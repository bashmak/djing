from typing import Optional, AnyStr

from jsonfield import JSONField
from django.db import models
from django.shortcuts import resolve_url
from django.utils.translation import gettext_lazy as _

from djing.lib.fields import MACAddressFieldUnixDialect
from djing.lib import MyChoicesAdapter
from groupapp.models import Group
from . import dev_types
from .base_intr import DevBase


# Maked compatible

class DeviceDBException(Exception):
    pass


class DeviceMonitoringException(Exception):
    pass


class Device(models.Model):
    _cached_manager = None

    ip_address = models.GenericIPAddressField(verbose_name=_('Ip address'), null=True, blank=True)
    mac_addr = MACAddressFieldUnixDialect(verbose_name=_('Mac address'), unique=True)
    comment = models.CharField(_('Comment'), max_length=256)
    DEVICE_TYPES = (
        # ('Dl', dev_types.DLinkDevice),
        # ('Pn', dev_types.OLTDevice),
        # ('On', dev_types.OnuDevice),
        # ('Ex', dev_types.EltexSwitch),
        # ('Zt', dev_types.Olt_ZTE_C320),
        # ('Zo', dev_types.ZteOnuDevice),
        # ('Z6', dev_types.ZteF601),
        # ('Hw', dev_types.HuaweiSwitch)
        (1, dev_types.DLinkDevice),
        (2, dev_types.OLTDevice),
        (3, dev_types.OnuDevice),
        (4, dev_types.EltexSwitch),
        (5, dev_types.Olt_ZTE_C320),
        (6, dev_types.ZteOnuDevice),
        (7, dev_types.ZteF601),
        (8, dev_types.HuaweiSwitch),
        #(9, dev_types.ZteF660v125s)
        (9, dev_types.DLinkDevice),
        (10, dev_types.DLinkDevice),
        (11, dev_types.DLinkDevice)
    )
    devtype = models.PositiveSmallIntegerField(_('Device type'), default=1,
                                               choices=MyChoicesAdapter(DEVICE_TYPES),
                                               db_column='dev_type')
    man_passw = models.CharField(_('SNMP password'), max_length=16, null=True, blank=True)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_('Device group'))
    parent_dev = models.ForeignKey('self', verbose_name=_('Parent device'), blank=True, null=True,
                                   on_delete=models.SET_NULL)

    snmp_extra = models.CharField(_('SNMP extra info'), max_length=256, null=True, blank=True)
    extra_data = JSONField(verbose_name=_('Extra data'),
                           help_text=_('Extra data in JSON format. You may use it for your custom data'),
                           blank=True, null=True)

    NETWORK_STATES = (
        # ('und', _('Undefined')),
        # ('up', _('Up')),
        # ('unr', _('Unreachable')),
        # ('dwn', _('Down'))
        (0, _('Undefined')),
        (1, _('Up')),
        (2, _('Unreachable')),
        (3, _('Down'))
    )
    status = models.PositiveSmallIntegerField(_('Status'), choices=NETWORK_STATES, default=0)

    is_noticeable = models.BooleanField(_('Send notify when monitoring state changed'), default=False)

    class Meta:
        db_table = 'device'
        verbose_name = _('Device')
        verbose_name_plural = _('Devices')
        ordering = ('id',)

    def get_manager_klass(self):
        try:
            return next(klass for code, klass in self.DEVICE_TYPES if code == self.devtype)
        except StopIteration:
            raise TypeError('one of types is not subclass of DevBase. '
                            'Or implementation of that device type is not found')

    def get_manager_object(self) -> DevBase:
        man_klass = self.get_manager_klass()
        if self._cached_manager is None:
            self._cached_manager = man_klass(self)
        return self._cached_manager

    # Can attach device to subscriber in subscriber page
    def has_attachable_to_subscriber(self) -> bool:
        mngr = self.get_manager_klass()
        return mngr.has_attachable_to_subscriber

    def __str__(self):
        return "%s: (%s) %s %s" % (self.comment, self.get_devtype_display(), self.ip_address or '', self.mac_addr or '')

    def generate_config_template(self) -> Optional[AnyStr]:
        mng = self.get_manager_object()
        return mng.monitoring_template()

    def register_device(self):
        mng = self.get_manager_object()
        if not self.extra_data:
            if self.parent_dev and self.parent_dev.extra_data:
                return mng.register_device(self.parent_dev.extra_data)
        return mng.register_device(self.extra_data)

    def get_absolute_url(self):
        return resolve_url('devapp:edit', self.group.pk, self.pk)


class Port(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, verbose_name=_('Device'))
    num = models.PositiveSmallIntegerField(_('Number'), default=0)
    descr = models.CharField(_('Description'), max_length=60, null=True, blank=True)
    PORT_OPERATING_MODES = (
        (0, _('Not chosen')),
        (1, _('Access')),
        (2, _('Trunk')),
        (3, _('Hybrid')),
        (4, _('General'))
    )
    operating_mode = models.PositiveSmallIntegerField(
        _('Operating mode'), default=0,
        choices=PORT_OPERATING_MODES
    )
    def __str__(self):
        return "%d: %s" % (self.num, self.descr)

    class Meta:
        db_table = 'device_port'
        unique_together = ('device', 'num')
        permissions = (
            ('can_toggle_ports', _('Can toggle ports')),
        )
        verbose_name = _('Port')
        verbose_name_plural = _('Ports')
        ordering = ('num',)
