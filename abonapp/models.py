from datetime import datetime
from typing import Optional

from encrypted_model_fields.fields import EncryptedCharField
from profiles.models import UserProfile, MyUserManager, BaseAccount
from bitfield import BitField
from django.conf import settings
from django.core import validators
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models.signals import post_init, pre_save
from django.dispatch import receiver
from django.shortcuts import resolve_url
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _, gettext
from djing.lib import LogicError
from groupapp.models import Group
from gw_app.nas_managers import SubnetQueue, NasFailedResult, NasNetworkError
from tariff_app.models import Tariff, PeriodicPay


# Maked compatible


class AbonLog(models.Model):
    abon = models.ForeignKey('Abon', on_delete=models.CASCADE, db_column='customer_id')
    amount = models.FloatField(default=0.0, db_column='cost')
    author = models.ForeignKey(
        UserProfile, on_delete=models.SET_NULL,
        related_name='+', blank=True, null=True
    )
    comment = models.CharField(max_length=128)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'customer_log'
        ordering = '-date',

    def __str__(self):
        return self.comment


class AbonTariff(models.Model):
    tariff = models.ForeignKey(
        Tariff,
        on_delete=models.CASCADE,
        related_name='linkto_tariff',
        db_column='service_id'
    )

    time_start = models.DateTimeField(null=True, blank=True, default=None, db_column='start_time')

    deadline = models.DateTimeField(null=True, blank=True, default=None)

    def calc_amount_service(self):
        amount = self.tariff.amount
        return round(amount, 2)

    def __str__(self):
        return "%s: %s" % (
            self.deadline,
            self.tariff.title
        )

    class Meta:
        db_table = 'customer_service'
        permissions = (
            ('can_complete_service', _('finish service perm')),
        )
        verbose_name = _('Abon service')
        verbose_name_plural = _('Abon services')
        ordering = ('time_start',)


class AbonStreet(models.Model):
    name = models.CharField(_('Street title'), max_length=64)
    group = models.ForeignKey(Group, verbose_name=_('User group'), on_delete=models.CASCADE)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'customer_street'
        verbose_name = _('Street')
        verbose_name_plural = _('Streets')
        ordering = 'name',


class AbonManager(MyUserManager):
    def get_queryset(self):
        return super(AbonManager, self).get_queryset().filter(is_admin=False)

    def filter_ip_address(self, group_ids: tuple, nas_id: int):
        nas_id = int(nas_id)
        if not isinstance(group_ids, tuple):
            group_ids = tuple(group_ids)
        return self.raw(
            'SELECT baseaccount_ptr_id, ip_address FROM customers '
            'WHERE group_id IN %s AND gateway_id=%s AND ip_address IS NOT NULL '
            'ORDER BY ip_address ASC',
            params=(group_ids, str(nas_id))
        )


class Abon(BaseAccount):
    current_tariff = models.OneToOneField(
        AbonTariff,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        default=None,
        db_column='current_service_id'
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        blank=True, null=True,
        verbose_name=_('User group')
    )
    ballance = models.FloatField(default=0.0, db_column='balance')
    ip_address = models.GenericIPAddressField(
        verbose_name=_('Ip address'),
        null=True,
        blank=True
    )
    description = models.TextField(
        _('Comment'),
        null=True,
        blank=True
    )
    street = models.ForeignKey(
        AbonStreet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Street')
    )
    house = models.CharField(
        _('House'),
        max_length=12,
        null=True,
        blank=True
    )
    device = models.ForeignKey(
        'devapp.Device',
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    dev_port = models.ForeignKey(
        'devapp.Port',
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    is_dynamic_ip = models.BooleanField(
        _('Is dynamic ip'),
        default=False
    )
    nas = models.ForeignKey(
        'gw_app.NASModel',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_('Network access server'),
        default=None,
        db_column='gateway_id'
    )
    autoconnect_service = models.BooleanField(
        _('Automatically connect next service'),
        default=False,
        db_column='auto_renewal_service'
    )
    last_connected_tariff = models.ForeignKey(
        Tariff, verbose_name=_('Last connected service'),
        on_delete=models.SET_NULL, null=True, blank=True, default=None,
        db_column='last_connected_service_id'
    )

    MARKER_FLAGS = (
        ('icon_donkey', _('Donkey')),
        ('icon_fire', _('Fire')),
        ('icon_ok', _('Ok')),
        ('icon_king', _('King')),
        ('icon_tv', _('TV')),
        ('icon_smile', _('Smile')),
        ('icon_dollar', _('Dollar')),
        ('icon_service', _('Service')),
        ('icon_mrk', _('Marker'))
    )
    markers = BitField(flags=MARKER_FLAGS, default=0)

    def get_flag_icons(self):
        """
        Return icon list of set flags from self.markers
        :return: ['m-icon-donkey', 'm-icon-tv', ...]
        """
        return tuple("m-%s" % name for name, state in self.markers if state)

    def active_tariff(self):
        return self.current_tariff

    objects = AbonManager()

    class Meta:
        db_table = 'customers'
        permissions = (
            ('can_buy_tariff', _('Buy service perm')),
            ('can_add_ballance', _('fill account')),
            ('can_ping', _('Can ping'))
        )
        verbose_name = _('Abon')
        verbose_name_plural = _('Abons')
        ordering = ('fio',)
        unique_together = ('ip_address', 'nas')

    def add_ballance(self, current_user, amount, comment):
        AbonLog.objects.create(
            abon=self,
            amount=amount,
            author=current_user if isinstance(current_user,
                                              UserProfile) else None,
            comment=comment
        )
        self.ballance += amount

    def pick_tariff(self, tariff, author, comment=None, deadline=None) -> None:
        """
        Trying to buy a service if enough money.
        :param tariff: instance of tariff_app.models.Tariff.
        :param author: Instance of profiles.models.UserProfile.
        Who connected this service. May be None if author is a system.
        :param comment: Optional text for logging this pay.
        :param deadline: Instance of datetime.datetime. Date when service is
        expired.
        :return: Nothing
        """
        if not isinstance(tariff, Tariff):
            raise TypeError

        amount = round(tariff.amount, 2)

        if tariff.is_admin and author is not None:
            if not author.is_staff:
                raise LogicError(
                    _('User that is no staff can not buy admin services')
                )

        if self.current_tariff is not None:
            if self.current_tariff.tariff == tariff:
                # if service already connected
                raise LogicError(_('That service already activated'))
            else:
                # if service is present then speak about it
                raise LogicError(_('Service already activated'))

        # if not enough money
        if self.ballance < amount:
            raise LogicError(_('%s not enough money for service %s') % (
                self.username, tariff.title
            ))

        with transaction.atomic():
            new_abtar = AbonTariff.objects.create(
                deadline=deadline, tariff=tariff
            )
            self.current_tariff = new_abtar
            if self.last_connected_tariff != tariff:
                self.last_connected_tariff = tariff

            # charge for the service
            self.ballance -= amount

            self.save(update_fields=(
                'ballance',
                'current_tariff',
                'last_connected_tariff'
            ))

            # make log about it
            AbonLog.objects.create(
                abon=self, amount=-tariff.amount,
                author=author if isinstance(author, UserProfile) else None,
                comment=comment or _('Buy service default log')
            )

    def attach_ip_addr(self, ip, strict=False):
        """
        Attach ip address to account
        :param ip: Instance of str or ip_address
        :param strict: If strict is True then ip not replaced quietly
        :return: None
        """
        if strict and self.ip_address:
            raise LogicError('Ip address already exists')
        self.ip_address = ip
        self.save(update_fields=('ip_address',))

    def free_ip_addr(self) -> bool:
        if self.ip_address:
            self.ip_address = None
            self.save(update_fields=('ip_address',))
            return True
        return False

    # is subscriber have access to service,
    # view in tariff_app.custom_tariffs.<TariffBase>.manage_access()
    def is_access(self) -> bool:
        if not self.is_active:
            return False
        abon_tariff = self.active_tariff()
        if abon_tariff is None:
            return False
        trf = abon_tariff.tariff
        ct = trf.get_calc_type()(abon_tariff)
        return ct.manage_access(self)

    # make subscriber from agent structure
    def build_agent_struct(self):
        if not self.ip_address:
            return
        abon_tariff = self.active_tariff()
        if abon_tariff:
            abon_tariff = abon_tariff.tariff
            return SubnetQueue(
                name="uid%d" % self.pk,
                network=self.ip_address,
                max_limit=(abon_tariff.speedIn, abon_tariff.speedOut),
                is_access=self.is_access()
            )

    def nas_sync_self(self) -> Optional[Exception]:
        """
        Synchronize user with gateway
        :return:
        """
        if self.nas is None:
            raise LogicError(_('gateway required'))
        try:
            agent_abon = self.build_agent_struct()
            if agent_abon is not None:
                mngr = self.nas.get_nas_manager()
                mngr.update_user(agent_abon)
        except (NasFailedResult, NasNetworkError, ConnectionResetError) as e:
            print('ERROR:', e)
            return e
        except LogicError:
            pass

    def nas_add_self(self):
        """
        Will add this user to network access server
        :return:
        """
        if self.nas is None:
            raise LogicError(_('gateway required'))
        try:
            agent_abon = self.build_agent_struct()
            if agent_abon is not None:
                mngr = self.nas.get_nas_manager()
                mngr.add_user(agent_abon)
        except (NasFailedResult, NasNetworkError, ConnectionResetError) as e:
            print('ERROR:', e)
            return e
        except LogicError:
            pass

    def get_absolute_url(self):
        return resolve_url('abonapp:abon_home', self.group.id, self.username)

    def enable_service(self, tariff: Tariff, deadline=None, time_start=None):
        """
        Makes a services for current user, without money
        :param tariff: Instance of service
        :param deadline: Time when service is expired
        :param time_start: Time when service has started
        :return: None
        """
        if deadline is None:
            deadline = tariff.calc_deadline()
        if time_start is None:
            time_start = datetime.now()
        new_abtar = AbonTariff.objects.create(
            deadline=deadline, tariff=tariff,
            time_start=time_start
        )
        self.current_tariff = new_abtar
        self.last_connected_tariff = tariff
        self.save(update_fields=('current_tariff', 'last_connected_tariff'))


class PassportInfo(models.Model):
    series = models.CharField(
        _('Pasport serial'),
        max_length=4,
        validators=(validators.integer_validator,)
    )
    number = models.CharField(
        _('Pasport number'),
        max_length=6,
        validators=(validators.integer_validator,)
    )
    distributor = models.CharField(
        _('Distributor'),
        max_length=64
    )
    date_of_acceptance = models.DateField(_('Date of acceptance'))
    abon = models.OneToOneField(
        Abon,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        db_column='customer_id'
    )

    class Meta:
        db_table = 'passport_info'
        verbose_name = _('Passport Info')
        verbose_name_plural = _('Passport Info')
        ordering = ('series',)

    def __str__(self):
        return "%s %s" % (self.series, self.number)


class InvoiceForPayment(models.Model):
    abon = models.ForeignKey(Abon, on_delete=models.CASCADE, db_column='customer_id')
    status = models.BooleanField(default=False)
    amount = models.FloatField(default=0.0, db_column='cost')
    comment = models.CharField(max_length=128)
    date_create = models.DateTimeField(auto_now_add=True)
    date_pay = models.DateTimeField(blank=True, null=True)
    author = models.ForeignKey(
        UserProfile,
        related_name='+',
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )

    def __str__(self):
        return "%s -> %.2f" % (self.abon.username, self.amount)

    def set_ok(self):
        self.status = True
        self.date_pay = timezone.now()

    class Meta:
        ordering = ('date_create',)
        db_table = 'customer_inv_pay'
        verbose_name = _('Debt')
        verbose_name_plural = _('Debts')


class AbonRawPassword(models.Model):
    account = models.OneToOneField(Abon, models.CASCADE, primary_key=True, db_column='customer_id')
    passw_text = EncryptedCharField(max_length=64)

    def __str__(self):
        return "%s - %s" % (self.account, self.passw_text)

    class Meta:
        db_table = 'customer_raw_password'


class AdditionalTelephone(models.Model):
    abon = models.ForeignKey(
        Abon,
        on_delete=models.CASCADE,
        related_name='additional_telephones',
        db_column='customer_id'
    )
    telephone = models.CharField(
        max_length=16,
        verbose_name=_('Telephone'),
        # unique=True,
        validators=(RegexValidator(
            getattr(settings, 'TELEPHONE_REGEXP', r'^(\+[7893]\d{10,11})?$')
        ),)
    )
    owner_name = models.CharField(_('Telephone owner'), max_length=127)

    def __str__(self):
        return "%s - (%s)" % (self.owner_name, self.telephone)

    class Meta:
        db_table = 'additional_telephones'
        ordering = ('owner_name',)
        verbose_name = _('Additional telephone')
        verbose_name_plural = _('Additional telephones')


class PeriodicPayForId(models.Model):
    periodic_pay = models.ForeignKey(
        PeriodicPay,
        on_delete=models.CASCADE,
        verbose_name=_('Periodic pay')
    )
    last_pay = models.DateTimeField(_('Last pay time'), blank=True, null=True)
    next_pay = models.DateTimeField(_('Next time to pay'))
    account = models.ForeignKey(
        Abon,
        on_delete=models.CASCADE,
        verbose_name=_('Account')
    )

    def payment_for_service(self, author: UserProfile = None, now=None):
        """
        Charge for the service and leave a log about it
        :param now: Current date, if now is None than it calculates in here
        :param author: instance of UserProfile
        """
        if now is None:
            now = timezone.now()
        if self.next_pay < now:
            pp = self.periodic_pay
            amount = pp.calc_amount()
            next_pay_date = pp.get_next_time_to_pay(self.last_pay)
            abon = self.account
            with transaction.atomic():
                abon.add_ballance(author, -amount, comment=gettext(
                    'Charge for "%(service)s"') % {
                        'service': self.periodic_pay
                    })
                abon.save(update_fields=('ballance',))
                self.last_pay = now
                self.next_pay = next_pay_date
                self.save(update_fields=('last_pay', 'next_pay'))

    def __str__(self):
        return "%s %s" % (self.periodic_pay, self.next_pay)

    class Meta:
        db_table = 'periodic_pay_for_id'
        ordering = ('last_pay',)


@receiver(post_init, sender=AbonTariff)
def abon_tariff_post_init(sender, **kwargs):
    abon_tariff = kwargs["instance"]
    if getattr(abon_tariff, 'time_start') is None:
        abon_tariff.time_start = timezone.now()
    if getattr(abon_tariff, 'deadline') is None:
        calc_obj = abon_tariff.tariff.get_calc_type()(abon_tariff)
        abon_tariff.deadline = calc_obj.calc_deadline()


@receiver(pre_save, sender=AbonTariff)
def abon_tariff_pre_save(sender, **kwargs):
    abon_tariff = kwargs["instance"]
    if getattr(abon_tariff, 'deadline') is None:
        calc_obj = abon_tariff.tariff.get_calc_type()(abon_tariff)
        abon_tariff.deadline = calc_obj.calc_deadline()
