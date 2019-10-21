from django.contrib.messages import MessageFailure
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.shortcuts import resolve_url
from django.utils.translation import gettext_lazy as _
from django.db import models
from encrypted_model_fields.fields import EncryptedCharField
from djing.lib import MyChoicesAdapter
from gw_app.nas_managers import NAS_TYPES, NasNetworkError


# Maked compatible

class NASModel(models.Model):
    title = models.CharField(_('Title'), max_length=127, unique=True)
    ip_address = models.GenericIPAddressField(_('Ip address'), unique=True)
    ip_port = models.PositiveSmallIntegerField(_('Port'))
    auth_login = models.CharField(_('Auth login'), max_length=64)
    auth_passw = EncryptedCharField(_('Auth password'), max_length=127)
    nas_type = models.PositiveSmallIntegerField(_('Type'), choices=MyChoicesAdapter(NAS_TYPES), default=0, db_column='gw_type')
    default = models.BooleanField(_('Is default'), default=False, db_column='is_default')
    enabled = models.BooleanField(_('Enabled'), default=True)

    def get_nas_manager_klass(self):
        try:
            return next(klass for code, klass in NAS_TYPES if code == self.nas_type)
        except StopIteration:
            raise TypeError(_('One of nas types implementation is not found'))

    def get_nas_manager(self):
        try:
            klass = self.get_nas_manager_klass()
            if hasattr(self, '_nas_mngr'):
                o = getattr(self, '_nas_mngr')
            else:
                o = klass(
                    login=self.auth_login,
                    password=self.auth_passw,
                    ip=self.ip_address,
                    port=int(self.ip_port),
                    enabled=bool(self.enabled)
                )
                setattr(self, '_nas_mngr', o)
            return o
        except ConnectionResetError:
            raise NasNetworkError('ConnectionResetError')

    def get_absolute_url(self):
        return resolve_url('gw_app:edit', self.pk)

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'gateways'
        verbose_name = _('Network access server. Gateway')
        verbose_name_plural = _('Network access servers. Gateways')
        ordering = 'ip_address',


@receiver(pre_delete, sender=NASModel)
def nas_pre_delete(sender, **kwargs):
    nas = kwargs.get("instance")
    # check if this nas is default.
    # You cannot remove default server
    if nas.default:
        raise MessageFailure(_('You cannot remove default server'))
