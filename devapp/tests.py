from hashlib import sha256
from django.shortcuts import resolve_url
from django.test import TestCase, RequestFactory, override_settings

from accounts_app.models import UserProfile
from devapp.models import Device
from group_app.models import Group

rf = RequestFactory()
API_SECRET = 'TestApiSecret'


def calc_hash(data):
    if type(data) is str:
        result_data = data.encode('utf-8')
    else:
        result_data = bytes(data)
    return sha256(result_data).hexdigest()


class DevTest(TestCase):
    def setUp(self):
        grp = Group.objects.create(title='Grp1')
        my_admin = UserProfile.objects.create_superuser('+79781234567', 'local_superuser', 'ps')
        # self.client.login(username=my_admin.username, password=my_admin.password)
        self.adminuser = my_admin
        Device.objects.create(
            ip_address='192.168.0.100',
            mac_addr='78:81:f2:1f:d2:a9',
            comment='Test device',
            devtype=3,
            man_passw='public',
            group=grp
        )

    @override_settings(API_AUTH_SECRET=API_SECRET, API_AUTH_SUBNET='127.0.0.1')
    def test_secure_api_ok(self):
        self.client.force_login(self.adminuser)
        sign = calc_hash(API_SECRET)
        url = resolve_url('devapp:nagios_get_all_hosts')
        r = self.client.get(url, {
            'sign': sign
        })
        self.assertEqual(r.status_code, 200)

    @override_settings(API_AUTH_SECRET=API_SECRET, API_AUTH_SUBNET='127.0.0.1')
    def test_get_config_nagios_file(self):
        self.client.force_login(self.adminuser)
        sign = calc_hash(API_SECRET)
        url = resolve_url('devapp:nagios_objects_conf')
        r = self.client.get(url, {
            'sign': sign
        })
        self.assertEqual(r.status_code, 200)
