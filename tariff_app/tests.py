from abc import ABCMeta

from django.conf import settings
from django.shortcuts import resolve_url
from django.test import TestCase

from profiles.models import UserProfile
from groupapp.models import Group
from tariff_app.models import Tariff


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


class ServiceTestCase(MyBaseTestCase, TestCase):
    def setUp(self):
        super(ServiceTestCase, self).setUp()
        trf = Tariff.objects.create(
            title='test',
            descr='Some descr',
            speedIn=10.0,
            speedOut=2.0,
            amount=1.0,
            calc_type=0
        )
        trf.groups.add(self.group.pk)
        self.tariff = trf

    def test_add_same_services(self):
        print('test_add_same_services')
        url = resolve_url('tariff_app:add')
        self._client_get_check_login(url)
        self.client.post(url, data={
            'title': 'same srv',
            'descr': 'descriptive',
            'speedIn': 10.0,
            'speedOut': 2.0,
            'amount': 1.0,
            'calc_type': 0
        })
        try:
            Tariff.objects.get(title='same srv')
            raise self.failureException('Services cannot be saved because it duplicates other service')
        except Tariff.DoesNotExist:
            pass
