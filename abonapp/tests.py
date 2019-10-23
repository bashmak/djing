from abc import ABCMeta
from hashlib import md5
from datetime import date

from profiles.models import UserProfile
from django.shortcuts import resolve_url
from django.test import TestCase, RequestFactory
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from abonapp.models import Abon, AbonStreet, PassportInfo
from groupapp.models import Group
from tariff_app.models import Tariff
from ip_pool.models import NetworkModel

rf = RequestFactory()


def _make_sign(act: int, pay_account: str, serv_id: str, pay_id):
    md = md5()
    secret = getattr(settings, 'PAY_SECRET')
    s = "%d_%s_%s_%s_%s" % (act, pay_account, serv_id, pay_id, secret)
    md.update(bytes(s, 'utf-8'))
    return md.hexdigest()


class MyBaseTestCase(metaclass=ABCMeta):
    def _client_get_check_login(self, url):
        """
        Checks if url is protected from unauthorized access
        :param url:
        :return: authorized response
        """
        r = self.client.get(url)
        self.assertRedirects(r, "%s?next=%s" % (getattr(settings, 'LOGIN_URL'), url))
        self.client.force_login(self.adminuser)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        return r

    def setUp(self):
        grp = Group.objects.create(title='Grp1')
        a1 = Abon.objects.create_user(
            telephone='+79781234567',
            username='abon',
            password='passw1'
        )
        a1.group = grp
        a1.save(update_fields=('group',))
        my_admin = UserProfile.objects.create_superuser('+79781234567', 'local_superuser', 'ps')
        self.adminuser = my_admin
        self.abon = a1
        self.group = grp


class StreetTestCase(MyBaseTestCase, TestCase):
    group = None
    street = None

    def setUp(self):
        super(StreetTestCase, self).setUp()
        grp = self.group
        self.street = AbonStreet.objects.create(name='test_street', group=grp)
        AbonStreet.objects.create(name='test_street1', group=grp)
        AbonStreet.objects.create(name='test_street2', group=grp)
        AbonStreet.objects.create(name='test_street3', group=grp)
        AbonStreet.objects.create(name='test_street4', group=grp)
        AbonStreet.objects.create(name='test_street5', group=grp)

    def test_street_make_cyrillic(self):
        print('test_make_cyrillic_street')
        # title = ''.join(chr(n) for n in range(1072, 1104))
        cyrrilic = 'абвгдежзийклмнопрстуфхцчшщъыьэюя'
        url = resolve_url('abonapp:street_add', self.group.pk)
        self._client_get_check_login(url)
        r = self.client.post(url, {
            'name': cyrrilic,
            'group': self.group.pk
        })
        # print(r, r.content.decode('utf-8'))
        self.assertEqual(r.status_code, 302)

    def test_street_edit(self):
        print('test_edit_steet')
        url = resolve_url('abonapp:street_edit', self.group.pk)
        streets = AbonStreet.objects.exclude(pk=self.street.pk)
        self._client_get_check_login(url)
        r = self.client.post(url, {
            'sid': tuple(s.id for s in streets),
            'sname': tuple('%s_' % s.name for s in streets)
        })
        streets = AbonStreet.objects.exclude(pk=self.street.pk)
        for street in streets:
            self.assertTrue(street.name.endswith('_'))
        self.assertEqual(r.status_code, 302)

    def test_street_del(self):
        print('test_street_del')
        self.client.force_login(self.adminuser)
        for street in AbonStreet.objects.exclude(pk=self.street.pk):
            url = resolve_url('abonapp:street_del', self.group.pk, street.pk)
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302)
        after_count = AbonStreet.objects.exclude(pk=self.street.pk).count()
        self.assertEqual(after_count, 0)


class PassportTestCase(MyBaseTestCase, TestCase):
    def setUp(self):
        super(PassportTestCase, self).setUp()
        passport_item = PassportInfo.objects.create(
            series='1243',
            number='738517',
            distributor='Distributor',
            date_of_acceptance=date(year=2014, month=9, day=14),
            abon=self.abon
        )
        self.passport = passport_item

    def test_create_update_delete(self):
        self.passport_make()
        self.passport_change()
        self.passport_remove_item_with_user()

    def passport_make(self):
        print('passport_make')
        url = resolve_url('abonapp:passport_view', self.group.pk, self.abon.username)
        self._client_get_check_login(url)
        self.client.post(url, {
            'series': '1232',
            'number': '123456',
            'distributor': 'Distrib',
            'date_of_acceptance': date(year=2013, month=1, day=17)
        })
        passport = PassportInfo.objects.filter(abon=self.abon).first()
        self.assertIsNotNone(passport)
        self.assertEqual('1232', passport.series)
        self.assertEqual('123456', passport.number)
        self.assertEqual('Distrib', passport.distributor)

    def passport_change(self):
        print('passport_change')
        url = resolve_url('abonapp:passport_view', self.group.pk, self.abon.username)
        self.client.post(url, {
            'series': '9876',
            'number': '987654',
            'distributor': 'Long new text distributor',
            'date_of_acceptance': date(year=1873, month=5, day=29)
        })
        passport = PassportInfo.objects.filter(abon=self.abon).first()
        self.assertIsNotNone(passport)
        self.assertEqual('9876', passport.series)
        self.assertEqual('987654', passport.number)
        self.assertEqual('Long new text distributor', passport.distributor)

    def passport_remove_item_with_user(self):
        print('passport_remove_item_with_user')
        url = resolve_url('abonapp:del_abon', self.group.pk, self.abon.username)
        self.client.post(url)
        passport = PassportInfo.objects.filter(abon=self.abon).first()
        self.assertIsNone(passport)


class AbonServiceTestCase(MyBaseTestCase, TestCase):

    def setUp(self):
        super().setUp()
        tariff1 = Tariff.objects.create(
            title='trf',
            descr='descr',
            speedIn=2,
            speedOut=5,
            amount=1,
            calc_type='Dp'
        )
        tariff1.groups.add(self.group)
        tariff2 = Tariff.objects.create(
            title='trf2',
            descr='descr2',
            speedIn=10,
            speedOut=10,
            amount=2,
            calc_type='Dp'
        )
        tariff2.groups.add(self.group)
        self.tariff1 = tariff1
        self.tariff2 = tariff2

    def test_refill_account(self):
        print('test_deposit_account')
        url = resolve_url('abonapp:abon_amount', gid=self.group.pk, uname=self.abon.username)
        self._client_get_check_login(url)
        self.client.post(url, data={
            'amount': 10.0,
            'comment': 'Test pay'
        })
        updated_abon = Abon.objects.get(username=self.abon.username)
        self.assertEqual(updated_abon.ballance, 10.0, msg='Account has no money')

    def test_attach_services_to_groups(self):
        print('test_attach_to_groups')
        url = resolve_url('abonapp:ch_group_tariff', gid=self.group.pk)
        self._client_get_check_login(url)
        self.client.post(url, data={
            'tr': ('1', '2')
        })
        updated_group = Group.objects.get(pk=self.group.pk)
        trfs_list = tuple(int(t.pk) for t in updated_group.tariff_set.all())
        self.assertTupleEqual((1, 2), trfs_list)

    def test_pick_service(self):
        print('test_pick_service')
        url = resolve_url('abonapp:pick_tariff', gid=self.group.pk, uname=self.abon.username)
        self._client_get_check_login(url)

        self.client.post(url, data={
            'tariff': self.tariff1.pk,
            'deadline': self.tariff1.calc_deadline()
        })
        # not enough money
        updated_abon = Abon.objects.get(username=self.abon.username)
        self.assertIsNone(updated_abon.current_tariff)

        # Try buying with positive ballance
        updated_abon.add_ballance(self.adminuser, 10, comment='Test amount')
        updated_abon.save(update_fields=('ballance',))
        self.client.post(url, data={
            'tariff': self.tariff1.pk,
            'deadline': self.tariff1.calc_deadline().strftime('%Y-%m-%d %H:%M:%S')
        })
        updated_abon = Abon.objects.get(username=self.abon.username)
        self.assertEqual(
            updated_abon.current_tariff.tariff.pk,
            self.tariff1.pk
        )
        self.assertEqual(
            updated_abon.ballance, 9.0
        )


class ClientLeasesTestCase(MyBaseTestCase, TestCase):
    def setUp(self):
        super(ClientLeasesTestCase, self).setUp()
        netw = NetworkModel.objects.create(
            network='192.168.0.0/24',
            kind='inet',
            description='Descr',
            ip_start='192.168.0.3',
            ip_end='192.168.0.6'
        )
        netw.groups.add(self.group.pk)
        self.network = netw
        netw6 = NetworkModel.objects.create(
            network='fde8:86a9:f132:1::/64',
            kind='inet',
            description='Descr',
            ip_start='fde8:86a9:f132:1::1',
            ip_end='fde8:86a9:f132:1::2f'
        )
        netw6.groups.add(self.group.pk)
        self.network6 = netw6

    def test_add_static_ipv4_lease(self):
        print('test_add_static_ipv4_lease')
        url = resolve_url('abonapp:lease_add', gid=self.group.pk, uname=self.abon.username)
        self._client_get_check_login(url)

        # Checks if lease not in allowed range
        r = self.client.post(url, data={
            'ip_addr': '192.168.0.255',
            'is_dynamic': False,
            'possible_networks': self.network.pk
        })
        self.assertFormError(r, form='form', field='ip_addr', errors=_('Ip that you have passed is greater than allowed network range'))

        # Not valid ipv4 address
        r = self.client.post(url, data={
            'ip_addr': '192.168.3.213123',
            'is_dynamic': False,
            'possible_networks': self.network.pk
        })
        self.assertFormError(r, form='form', field='ip_addr', errors=_('Enter a valid IPv4 or IPv6 address.'))

        # different subnet
        r = self.client.post(url, data={
            'ip_addr': '192.168.4.2',
            'is_dynamic': False,
            'possible_networks': self.network.pk
        })
        self.assertFormError(r, form='form', field='ip_addr', errors=_('Ip that you typed is not in subnet that you have selected'))

        # another subnet
        netw = NetworkModel.objects.create(
            network='192.168.1.0/24',
            kind='inet',
            description='Descr',
            ip_start='192.168.1.3',
            ip_end='192.168.1.6'
        )
        r = self.client.post(url, data={
            'ip_addr': '192.168.0.9',
            'is_dynamic': False,
            'possible_networks': netw.pk
        })
        self.assertFormError(r, form='form', field='ip_addr', errors=_('Ip that you typed is not in subnet that you have selected'))

        # successfully apply
        r = self.client.post(url, data={
            'ip_addr': '192.168.0.3',
            'is_dynamic': False,
            'possible_networks': self.network.pk
        })
        self.assertRedirects(r, resolve_url('abonapp:abon_home', self.group.pk, self.abon.username))
        updated_abon = Abon.objects.get(username=self.abon.username)
        ip_addr = updated_abon.ip_addresses.all().first()
        self.assertEqual('192.168.0.3', ip_addr.ip)

    def test_add_static_ipv6_lease(self):
        print('test_add_static_ipv6_lease')
        url = resolve_url('abonapp:lease_add', gid=self.group.pk, uname=self.abon.username)
        self._client_get_check_login(url)

        # Checks if lease not in allowed range
        r = self.client.post(url, data={
            'ip_addr': 'fde8:86a9:f132:1::3f',
            'is_dynamic': False,
            'possible_networks': self.network6.pk
        })
        self.assertFormError(r, form='form', field='ip_addr', errors=_('Ip that you have passed is greater than allowed network range'))

        # Not valid ipv4 address
        r = self.client.post(url, data={
            'ip_addr': 'fde8:86a9:f132:1::dsf',
            'is_dynamic': False,
            'possible_networks': self.network6.pk
        })
        self.assertFormError(r, form='form', field='ip_addr', errors=_('This is not a valid IPv6 address.'))

        # different subnet
        r = self.client.post(url, data={
            'ip_addr': 'fde8:86a9:f232:1::7',
            'is_dynamic': False,
            'possible_networks': self.network6.pk
        })
        self.assertFormError(r, form='form', field='ip_addr', errors=_('Ip that you typed is not in subnet that you have selected'))

        # another subnet
        netw = NetworkModel.objects.create(
            network='fde8:86a9:f132:1::1',
            kind='inet',
            description='Descr',
            ip_start='fde8:86a9:f132:1::2',
            ip_end='fde8:86a9:f132:1::ff12'
        )
        r = self.client.post(url, data={
            'ip_addr': 'fde8:86a9:f1c6:1::1',
            'is_dynamic': False,
            'possible_networks': netw.pk
        })
        self.assertFormError(r, form='form', field='ip_addr', errors=_('Ip that you typed is not in subnet that you have selected'))

        # successfully apply
        r = self.client.post(url, data={
            'ip_addr': 'fde8:86a9:f132:1::7',
            'is_dynamic': False,
            'possible_networks': self.network6.pk
        })
        self.assertRedirects(r, resolve_url('abonapp:abon_home', self.group.pk, self.abon.username))
        updated_abon = Abon.objects.get(username=self.abon.username)
        ip_addr = updated_abon.ip_addresses.all().first()
        self.assertEqual('fde8:86a9:f132:1::7', ip_addr.ip)
