from abc import ABCMeta

from abonapp.models import Abon
from profiles.models import UserProfile
from django.conf import settings
from django.shortcuts import resolve_url
from django.test import TestCase, override_settings
from groupapp.models import Group
from gw_app.models import NASModel
from gw_app.nas_managers import MikrotikTransmitter


class MyBaseTestCase(metaclass=ABCMeta):
    def _client_get_check_login(self, url):
        """
        Checks if url is protected from unauthorized access
        :param url:
        :return: authorized response
        """
        r = self.client.get(url)
        self.assertRedirects(
            r, "%s?next=%s" % (
                getattr(settings, 'LOGIN_URL'), url
            )
        )
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
        my_admin = UserProfile.objects.create_superuser(
            '+79781234567',
            'local_superuser', 'ps'
        )
        self.adminuser = my_admin
        self.abon = a1
        self.group = grp


class NASModelTestCase(MyBaseTestCase, TestCase):
    def setUp(self):
        super(NASModelTestCase, self).setUp()
        nas = NASModel.objects.create(
            title='Title',
            ip_address='192.168.8.12',
            ip_port=123,
            auth_login='admin',
            auth_passw='admin',
            default=True,
            nas_type=0
        )
        self.nas = nas

    @override_settings(LANGUAGE_CODE='en', LANGUAGES=(('en', 'English'),))
    def test_create(self):
        url = resolve_url('gw_app:add')
        self._client_get_check_login(url)

        # test success create nas
        r = self.client.post(url, data={
            'title': 'Test success nas',
            'ip_address': '192.168.8.10',
            'ip_port': 1254,
            'auth_login': '_',
            'auth_passw': '_',
            'nas_type': 0
        })
        self.assertEqual(r.status_code, 302)
        msg = r.cookies.get('messages')
        self.assertIn('New NAS has been created', msg.output())
        NASModel.objects.get(
            title='Test success nas',
            ip_address='192.168.8.10',
            ip_port=1254, auth_login='_',
            auth_passw='_'
        )

        # test error ip_port big range
        r = self.client.post(url, data={
            'title': 'New nas',
            'ip_address': '192.168.8.13',
            'ip_port': 8755877855798,
            'auth_login': '_',
            'auth_passw': '_'
        })
        self.assertEqual(r.status_code, 200)
        self.assertFormError(
            response=r, form='form', field='ip_port',
            errors='Ensure this value is less than or equal to %(limit_value)s.' % {
                'limit_value': 32767
            })

        # test get request
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

        # test error duplicates title
        r = self.client.post(url, data={
            'title': 'Test success nas',
            'ip_address': '192.168.8.14',
            'ip_port': 2543,
            'auth_login': '_w',
            'auth_passw': '_v'
        })
        self.assertEqual(r.status_code, 200)
        self.assertFormError(
            response=r, form='form', field='title',
            errors='%(model_name)s with this %(field_label)s already exists.' % {
                'model_name': NASModel._meta.verbose_name,
                'field_label': NASModel._meta.get_field('title').verbose_name
            }
        )

        # test error duplicates default
        r = self.client.post(url, data={
            'title': 'New again nas',
            'ip_address': '192.168.8.15',
            'ip_port': 9873,
            'auth_login': '_w',
            'auth_passw': '_v',
            'default': True
        })
        self.assertEqual(r.status_code, 200)
        self.assertFormError(
            response=r, form='form', field='default',
            errors='Can be only one default gateway'
        )

        # test error duplicates ip_address
        r = self.client.post(url, data={
            'title': 'New again nas2',
            'ip_address': '192.168.8.10',
            'ip_port': 1254,
            'auth_login': '_w',
            'auth_passw': '_v'
        })
        self.assertEqual(r.status_code, 200)
        self.assertFormError(
            response=r, form='form', field='ip_address',
            errors='%(model_name)s with this %(field_label)s already exists.' % {
                'model_name': NASModel._meta.verbose_name,
                'field_label': NASModel._meta.get_field(
                    'ip_address'
                ).verbose_name
            })

    @override_settings(LANGUAGE_CODE='en', LANGUAGES=(('en', 'English'),))
    def test_change(self):
        url = resolve_url('gw_app:edit', self.nas.pk)
        self._client_get_check_login(url)

        # test get request
        self.client.get(url)

        # test success change
        r = self.client.post(url, data={
            'title': 'New again nas2 changed',
            'ip_address': '192.168.8.12',
            'ip_port': 7865,
            'auth_login': '_w_c',
            'auth_passw': '_v_c',
            'nas_type': 0
        })
        self.assertRedirects(r, resolve_url('gw_app:edit', self.nas.pk))
        msg = r.cookies.get('messages')
        self.assertIn('Update successfully', msg.output())
        NASModel.objects.get(
            title='New again nas2 changed', ip_address='192.168.8.12',
            ip_port=7865, auth_login='_w_c', auth_passw='_v_c'
        )

    @override_settings(LANGUAGE_CODE='en', LANGUAGES=(('en', 'English'),))
    def test_delete(self):
        url = resolve_url('gw_app:add')
        self._client_get_check_login(url)
        r = self.client.post(url, data={
            'title': 'Test success nas_2',
            'ip_address': '192.168.8.11',
            'ip_port': 1254,
            'auth_login': '_',
            'auth_passw': '_',
            'nas_type': 0
        })
        self.assertEqual(r.status_code, 302)
        o = NASModel.objects.get(
            title='Test success nas_2', ip_address='192.168.8.11',
            ip_port=1254, auth_login='_', auth_passw='_'
        )
        url = resolve_url('gw_app:del', o.pk)

        # test get request
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

        # test deleting
        r = self.client.post(url)
        self.assertRedirects(r, resolve_url('gw_app:home'))
        msg = r.cookies.get('messages')
        self.assertIn('Server successfully removed', msg.output())
        try:
            NASModel.objects.get(title='Test success nas_2')
            raise self.failureException("NAS not removed")
        except NASModel.DoesNotExist:
            pass

        # try to remove default nas
        nas_id = self.nas.pk
        r = self.client.post(resolve_url('gw_app:del', nas_id))
        # self.assertRedirects(
        #     r, expected_url=resolve_url('gw_app:edit', nas_id)
        # )
        msg = r.cookies.get('messages')
        self.assertIn('You cannot remove default server', msg.output())

    def test_get_nas_manager(self):
        r = self.nas.get_nas_manager_klass()
        self.assertIs(r, MikrotikTransmitter)
        r = self.nas.get_nas_manager()
        self.assertIsInstance(r, MikrotikTransmitter)
