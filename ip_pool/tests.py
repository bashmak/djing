from abc import ABCMeta

from django.conf import settings
from django.shortcuts import resolve_url
from django.test import TestCase, override_settings

from profiles.models import UserProfile
from groupapp.models import Group
from ip_pool.models import NetworkModel


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
        my_admin = UserProfile.objects.create_superuser('+79781234567', 'local_superuser', 'ps')
        self.adminuser = my_admin
        self.group = grp


class NetworksTestCase(MyBaseTestCase, TestCase):
    def setUp(self):
        super(NetworksTestCase, self).setUp()
        netw = NetworkModel.objects.create(
            network='192.168.23.0/24',
            kind='inet',
            description='SomeDescr',
            ip_start='192.168.23.2',
            ip_end='192.168.23.254'
        )
        netw.groups.add(self.group.pk)
        self.network = netw

    @override_settings(LANGUAGE_CODE='en', LANGUAGES=(('en', 'English'),))
    def test_add_network(self):
        print('test_add_network')
        url = resolve_url('ip_pool:net_add')
        self._client_get_check_login(url)

        # Ip outside range
        r = self.client.post(url, data={
            'network': '192.168.23.0/24',
            'kind': 'inet',
            'description': 'SomeDescr',
            'ip_start': '192.168.23.2',
            'ip_end': '192.168.24.254'
        })
        self.assertFormError(r, form='form', field='ip_end', errors='End ip must be in subnet of specified network')

        # Invalid ip
        r = self.client.post(url, data={
            'network': '192.168.23.0/24',
            'kind': 'inet',
            'description': 'SomeDescr',
            'groups': (self.group.pk,),
            'ip_start': '192.168.23.2',
            'ip_end': '192.168.23.g'
        })
        self.assertFormError(r, form='form', field='ip_end', errors='Enter a valid IPv4 or IPv6 address.')

        # Not existed group
        r = self.client.post(url, data={
            'network': '192.168.23.0/24',
            'kind': 'inet',
            'description': 'SomeDescr',
            'groups': ('123',),  # Not existed group id
            'ip_start': '192.168.23.2',
            'ip_end': '192.168.23.6'
        })
        self.assertFormError(
            r, form='form', field='groups',
            errors='Select a valid choice. %(value)s is not one of the available choices.' % {
                'value': 123  # Not existed group id
            }
        )

        # Successfully add
        r = self.client.post(url, data={
            'network': '192.168.12.0/24',
            'kind': 'inet',
            'description': 'SomeDescr',
            'groups': (self.group.pk,),
            'ip_start': '192.168.12.2',
            'ip_end': '192.168.12.254'
        })
        added_net = NetworkModel.objects.get(description='SomeDescr', network='192.168.12.0/24', kind='inet')
        self.assertRedirects(r, resolve_url('ip_pool:net_edit', added_net.pk))
        self.assertEqual('192.168.12.0/24', str(added_net.network))
        self.assertEqual('inet', added_net.kind)
        self.assertEqual('SomeDescr', added_net.description)
        self.assertEqual(self.group.pk, added_net.groups.all().first().pk)
        self.assertEqual('192.168.12.2', str(added_net.ip_start))
        self.assertEqual('192.168.12.254', str(added_net.ip_end))

    @override_settings(LANGUAGE_CODE='en', LANGUAGES=(('en', 'English'),))
    def test_edit_network(self):
        print('test_edit_network')
        url = resolve_url('ip_pool:net_edit', net_id=self.network.pk)
        self._client_get_check_login(url)
        r = self.client.post(url, data={
            'network': '192.168.0.0/24',
            'kind': 'guest',
            'description': 'Описание',
            'groups': (self.group.pk,),
            'ip_start': '192.168.0.2',
            'ip_end': '192.168.0.254'
        })
        self.assertRedirects(r, resolve_url('ip_pool:net_edit', self.network.pk))
        updated_network = NetworkModel.objects.get(pk=self.network.pk)
        self.assertEqual('192.168.0.0/24', str(updated_network.network))
        self.assertEqual('guest', updated_network.kind)
        self.assertEqual('Описание', updated_network.description)
        self.assertEqual(self.group.pk, updated_network.groups.all().first().pk)
        self.assertEqual('192.168.0.2', str(updated_network.ip_start))
        self.assertEqual('192.168.0.254', str(updated_network.ip_end))

    def test_remove_network(self):
        print('test_remove_network')
        url = resolve_url('ip_pool:net_delete', net_id=self.network.pk)
        self._client_get_check_login(url)
        r = self.client.post(url)
        self.assertRedirects(r, resolve_url('ip_pool:networks'))
        try:
            NetworkModel.objects.get(pk=self.network.pk)
            raise self.failureException('Network must will be deleted')
        except NetworkModel.DoesNotExist:
            pass
