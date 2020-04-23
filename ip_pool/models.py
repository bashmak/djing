from ipaddress import ip_network, ip_address
from typing import Optional, Generator

from django.core.validators import MinValueValidator, MaxValueValidator
from django.shortcuts import resolve_url
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from netfields import InetAddressField
from groupapp.models import Group


# Maked compatible

class VlanIf(models.Model):
    title = models.CharField(_('Vlan title'), max_length=128)
    vid = models.PositiveSmallIntegerField(_('VID'), default=1, validators=[
        MinValueValidator(2, message=_('Vid could not be less then 2')),
        MaxValueValidator(4094, message=_('Vid could not be more than 4094'))
    ], unique=True)
    is_management = models.BooleanField(_('Is management'), default=False)

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'networks_vlan'
        ordering = ('-id',)
        verbose_name = _('Vlan')
        verbose_name_plural = _('Vlan list')


class NetworksIpPoolGroups(models.Model):
    group = models.ForeignKey(Group, db_column='group_id', on_delete=models.CASCADE)
    ippool = models.ForeignKey('NetworkModel', db_column='networkippool_id', on_delete=models.CASCADE)

    class Meta:
        db_table = 'networks_ippool_groups'


class NetworkModel(models.Model):
    _netw_cache = None

    network = InetAddressField(
        verbose_name=_('IP network'),
        help_text=_('Ip address of network. For example: '
                    '192.168.1.0 or fde8:6789:1234:1::'),
        unique=True
    )
    NETWORK_KINDS = (
        # ('inet', _('Internet')),
        # ('guest', _('Guest')),
        # ('trust', _('Trusted')),
        # ('device', _('Devices')),
        # ('admin', _('Admin'))
        (0, _('Not defined')),
        (1, _('Internet')),
        (2, _('Guest')),
        (3, _('Trusted')),
        (4, _('Devices')),
        (5, _('Admin'))
    )
    kind = models.PositiveSmallIntegerField(
        _('Kind of network'),
        choices=NETWORK_KINDS, default=0
    )
    description = models.CharField(_('Description'), max_length=64)
    groups = models.ManyToManyField(
        Group, verbose_name=_('Groups'),
        through=NetworksIpPoolGroups,
        through_fields=('ippool', 'group')
    )

    # Usable ip range
    ip_start = models.GenericIPAddressField(_('Start work ip range'))
    ip_end = models.GenericIPAddressField(_('End work ip range'))

    vlan_if = models.ForeignKey(
        VlanIf, verbose_name=_('Vlan interface'),
        on_delete=models.CASCADE, blank=True,
        null=True, default=None
    )

    gateway = models.GenericIPAddressField(_('Gateway ip address'))

    def __str__(self):
        netw = self.get_network()
        return "%s: %s" % (self.description, netw.with_prefixlen)

    def get_network(self):
        if self.network is None:
            return
        if self._netw_cache is None:
            self._netw_cache = ip_network(self.network)
        return self._netw_cache

    def get_absolute_url(self):
        return resolve_url('ip_pool:net_edit', self.pk)

    def clean(self):
        errs = {}
        if self.network is None:
            errs['network'] = ValidationError(
                _('Network is invalid'),
                code='invalid'
            )
            raise ValidationError(errs)
        net = self.get_network()
        if self.ip_start is None:
            errs['ip_start'] = ValidationError(
                _('Ip start is invalid'),
                code='invalid'
            )
            raise ValidationError(errs)
        start_ip = ip_address(self.ip_start)
        if start_ip not in net:
            errs['ip_start'] = ValidationError(
                _('Start ip must be in subnet of specified network'),
                code='invalid'
            )
        if self.ip_end is None:
            errs['ip_end'] = ValidationError(
                _('Ip end is invalid'),
                code='invalid'
            )
            raise ValidationError(errs)
        end_ip = ip_address(self.ip_end)
        if end_ip not in net:
            errs['ip_end'] = ValidationError(
                _('End ip must be in subnet of specified network'),
                code='invalid'
            )
        if errs:
            raise ValidationError(errs)

        other_nets = NetworkModel.objects.exclude(
            pk=self.pk
        ).only('network').order_by('network')
        if not other_nets.exists():
            return
        for onet in other_nets.iterator():
            onet_netw = onet.get_network()
            if net.overlaps(onet_netw):
                errs['network'] = ValidationError(
                    _('Network is overlaps with %(other_network)s'),
                    params={
                        'other_network': str(onet_netw)
                    }
                )
                raise ValidationError(errs)

    def get_scope(self) -> str:
        net = self.get_network()
        if net.is_global:
            return _('Global')
        elif net.is_link_local:
            return _('Link local')
        elif net.is_loopback:
            return _('Loopback')
        elif net.is_multicast:
            return _('Multicast')
        elif net.is_private:
            return _('Private')
        elif net.is_reserved:
            return _('Reserved')
        elif net.is_site_local:
            return _('Site local')
        elif net.is_unspecified:
            return _('Unspecified')
        return "I don't know"

    def get_free_ip(self, employed_ips: Optional[Generator]):
        """
        Find free ip in network.
        :param employed_ips: Sorted from less to more
         ip addresses from current network.
        :return: single found ip
        """
        network = self.get_network()
        work_range_start_ip = ip_address(self.ip_start)
        work_range_end_ip = ip_address(self.ip_end)
        if employed_ips is None:
            for ip in network.hosts():
                if work_range_start_ip <= ip <= work_range_end_ip:
                    return ip
            return
        for ip in network.hosts():
            if ip < work_range_start_ip:
                continue
            elif ip > work_range_end_ip:
                break  # Not found
            try:
                used_ip = next(employed_ips)
            except StopIteration:
                return ip
            if used_ip is None:
                return ip
            used_ip = ip_address(used_ip)
            if ip < used_ip:
                return ip

    class Meta:
        db_table = 'networks_ip_pool'
        verbose_name = _('Network')
        verbose_name_plural = _('Networks')
        ordering = ('network',)
