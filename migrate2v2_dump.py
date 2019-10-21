#!/usr/bin/env python
import os
from json import dump

from bitfield import BitField
from django import setup
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import ImageField, ManyToManyField, ManyToOneRel

from djing.fields import MACAddressField


class BatchSaveStreamList(list):
    def __init__(self, model_queryset, model_name, except_fields=None, choice_list_map=None, field_name_map=None, *args,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self._qs = model_queryset
        self._model_name = model_name
        self._except_fields = (except_fields or []) + ['id']
        self._choice_list_map = choice_list_map or {}
        self._field_name_map = field_name_map or {}
        print(model_name, end='\t' * 3)

    def _map_field_name(self, name):
        if name in self._field_name_map:
            return self._field_name_map.get(name)
        return name

    def _fields(self, obj):
        fls = obj._meta.get_fields()
        return {self._map_field_name(ob.name): self._field_val(obj, ob) for ob in fls if
                ob.name not in self._except_fields and ob.concrete}

    def __iter__(self):
        for d in self._qs.iterator():
            yield {
                "model": self._model_name,
                "pk": d.pk,
                "fields": self._fields(d)
            }

    def _field_val(self, obj, field):
        # choice fields
        if field.name in self._choice_list_map.keys():
            val = getattr(obj, field.name)
            return self._choice_list_map[field.name].get(val)

        # bit fields
        elif isinstance(field, BitField):
            val = getattr(obj, field.name)
            # val is instance of BitHandler
            return int(val)

        # image fields
        elif isinstance(field, ImageField):
            val = getattr(obj, field.name)
            return getattr(val, 'name') if val else None

        # mac address validated by netaddr.EUI
        elif isinstance(field, MACAddressField):
            val = getattr(obj, field.name)
            return str(val)

        # related fields
        if field.is_relation:
            if isinstance(field, ManyToOneRel):
                return getattr(obj, field.field_name)
            val = getattr(obj, field.attname)
            if isinstance(field, ManyToManyField):
                s = val.only('pk').values_list('pk', flat=True)
                return tuple(s)
            return val

        # all other simple fields
        else:
            v = getattr(obj, field.name)
            if isinstance(v, bool):
                return v
            if field.null:
                return v or None
            return v

    def __len__(self):
        return 1


def batch_save(app_label: str, fname: str, *args, **kwargs):
    sa = BatchSaveStreamList(*args, **kwargs)
    fixt_dir = os.path.join('fixtures', app_label, 'fixtures')
    if not os.path.isdir(fixt_dir):
        os.makedirs(fixt_dir, mode=0o750)
    full_path = os.path.join(fixt_dir, fname)
    print(full_path)
    with open(full_path, 'w') as f:
        dump(sa, f, ensure_ascii=False, indent=2, cls=DjangoJSONEncoder)


# ---------------------


def dump_groups():
    from group_app.models import Group
    batch_save(app_label='groupapp', fname="groups.json", model_queryset=Group.objects.all(), model_name='groupapp.group')


def dump_accounts():
    from accounts_app.models import UserProfile, BaseAccount, UserProfileLog
    app_label = 'profiles'
    batch_save(app_label=app_label, fname='accounts_baseaccount.json', model_queryset=BaseAccount.objects.exclude(username='AnonymousUser'), model_name='profiles.baseaccount',
               except_fields=['groups', 'user_permissions'])
    batch_save(app_label=app_label, fname='accounts_userprofile.json', model_queryset=UserProfile.objects.exclude(username='AnonymousUser'), model_name='profiles.userprofile',
               except_fields=['groups', 'user_permissions'])
    do_type_map = {
        'cusr': 1, 'dusr': 2,
        'cdev': 3, 'ddev': 4,
        'cnas': 5, 'dnas': 6,
        'csrv': 7, 'dsrv': 8
    }
    batch_save(app_label=app_label, fname='accounts_userprofilelog.json', model_queryset=UserProfileLog.objects.all(), model_name='profiles.userprofilelog',
               except_fields=['meta_info'],
               choice_list_map={
                   'do_type': do_type_map
               })


def dump_messenger():
    from messenger.models import Messenger, ViberMessenger, ViberMessage, ViberSubscriber
    app_label = 'messenger'
    batch_save(app_label, "messenger.json", Messenger.objects.all(), 'messenger.messenger')
    batch_save(app_label, "vibermessenger.json", ViberMessenger.objects.all(), 'messenger.vibermessenger')
    batch_save(app_label, "vibermessage.json", ViberMessage.objects.all(), 'messenger.vibermessage')
    batch_save(app_label, "vibersubscriber.json", ViberSubscriber.objects.all(), 'messenger.vibersubscriber')


def dump_services():
    from tariff_app.models import Tariff, PeriodicPay
    app_label = 'services'
    batch_save(app_label, "services.json", Tariff.objects.all(), 'services.service', field_name_map={
        'speedIn': 'speed_in',
        'speedOut': 'speed_out',
        'amount': 'cost'
    }, choice_list_map={
        'calc_type': {
            'Df': 0,
            'Dp': 1,
            'Cp': 2,
            'Dl': 3
        }
    })
    batch_save(app_label, "services_periodicpay.json", PeriodicPay.objects.all(), 'services.periodicpay', choice_list_map={
        'calc_type': {
            'df': 0,
            'cs': 1
        }
    })


def dump_gateways():
    from gw_app.models import NASModel
    app_label = 'gateways'
    batch_save(app_label, "gateways.json", NASModel.objects.all(), 'gateways.gateway', field_name_map={
        'nas_type': 'gw_type',
        'default': 'is_default'
    }, choice_list_map={
        'nas_type': {
            'mktk': 0
        }
    })


def dump_devices():
    from devapp.models import Device, Port
    app_label = 'devices'
    batch_save(app_label, "devices.json", Device.objects.all(), 'devices.device', field_name_map={
        'devtype': 'dev_type'
    }, choice_list_map={
        'devtype': {
            'Dl': 1, 'Pn': 2,
            'On': 3, 'Ex': 4,
            'Zt': 5, 'Zo': 6,
            'Z6': 7, 'Hw': 8
        },
        'status': {
            'und': 0,
            'up': 1,
            'unr': 2,
            'dwn': 3
        }
    })
    batch_save(app_label, 'devices_port.json', Port.objects.all(), 'devices.port')


def dump_customers():
    from abonapp.models import (
        Abon, AbonLog, AbonTariff, AbonStreet,
        PassportInfo, InvoiceForPayment, AbonRawPassword,
        AdditionalTelephone, PeriodicPayForId
    )
    app_label = 'customers'
    batch_save(app_label, 'customer.json', Abon.objects.exclude(username='AnonymousUser'), 'customers.customer', field_name_map={
        'current_tariff': 'current_service',
        'ballance': 'balance',
        'nas': 'gateway',
        'autoconnect_service': 'auto_renewal_service',
        'last_connected_tariff': 'last_connected_service'
    }, except_fields=['groups', 'user_permissions'])
    batch_save(app_label, 'customers_log.json', AbonLog.objects.all(), 'customers.customerlog', field_name_map={
        'abon': 'customer',
        'amount': 'cost'
    })
    batch_save(app_label, 'customers_service.json', AbonTariff.objects.all(), 'customers.customerservice', field_name_map={
        'tariff': 'service',
        'time_start': 'start_time'
    })
    batch_save(app_label, 'customers_street.json', AbonStreet.objects.all(), 'customers.customerstreet')
    batch_save(app_label, 'customers_passport.json', PassportInfo.objects.all(), 'customers.passportinfo', field_name_map={
        'abon': 'customer'
    })
    batch_save(app_label, 'customers_inv.json', InvoiceForPayment.objects.all(), 'customers.invoiceforpayment', field_name_map={
        'abon': 'customer',
        'amount': 'cost'
    })
    batch_save(app_label, 'customers_passw.json', AbonRawPassword.objects.all(), 'customers.customerrawpassword', field_name_map={
        'account': 'customer'
    })
    batch_save(app_label, 'customers_tels.json', AdditionalTelephone.objects.all(), 'customers.additionaltelephone', field_name_map={
        'abon': 'customer'
    })
    batch_save(app_label, 'customers_tels.json', PeriodicPayForId.objects.all(), 'customers.periodicpayforid')


def dump_networks():
    from ip_pool.models import NetworkModel
    app_label = 'networks'
    batch_save(app_label, 'nets.json', NetworkModel.objects.all(), 'networks.networkmodel', choice_list_map={
        'kind': {
            'inet': 1,
            'guest': 2,
            'trust': 3,
            'device': 4,
            'admin': 5
        }
    })


def dump_tasks():
    from taskapp.models import Task, ExtraComment, ChangeLog
    app_label = 'tasks'
    batch_save(app_label, 'task.json', Task.objects.all(), 'tasks.task', field_name_map={
        'abon': 'customer'
    }, except_fields=['attachment'], choice_list_map={
        'priority': {
            'E': 0,
            'C': 1,
            'A': 2
        },
        'state': {
            'S': 0,
            'C': 1,
            'F': 2
        },
        'mode': {
            'na': 0, 'ic': 1,
            'yt': 2, 'rc': 3,
            'ls': 4, 'cf': 5,
            'cn': 6, 'pf': 7,
            'cr': 8, 'co': 9,
            'fc': 10, 'ni': 11,
            'ot': 12
        }
    })
    batch_save(app_label, 'task_comments.json', ExtraComment.objects.all(), 'tasks.extracomment')
    batch_save(app_label, 'task_log.json', ChangeLog.objects.all(), 'tasks.changelog', choice_list_map={
        'act_type': {
            'e': 1, 'c': 2,
            'd': 3, 'f': 4, 'b': 5
        }
    })


def dump_fin():
    from finapp.models import PayAllTimeGateway, AllTimePayLog
    app_label = 'fin_app'
    batch_save(app_label, 'fin_gws.json', PayAllTimeGateway.objects.all(), 'fin_app.payalltimegateway')
    batch_save(app_label, 'fin_logs.json', AllTimePayLog.objects.all(), 'fin_app.alltimepaylog', field_name_map={
        'abon': 'customer',
        'summ': 'sum'
    })


all_migrs = (
    dump_groups, dump_accounts, dump_messenger,
    dump_services, dump_gateways, dump_devices,
    dump_customers, dump_networks, dump_tasks,
    dump_fin
)

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djing.settings')
    setup()
    # dump_accounts()
    for migr in all_migrs:
        migr()
