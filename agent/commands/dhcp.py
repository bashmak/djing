from typing import Optional
from django.core.exceptions import MultipleObjectsReturned
from abonapp.models import Abon
from devapp.models import Device, Port


def dhcp_commit(client_ip: str, client_mac: str,
                switch_mac: str, switch_port: int) -> Optional[str]:
    try:
        dev = Device.objects.get(mac_addr=switch_mac)
        mngr_class = dev.get_manager_klass()

        if mngr_class.get_is_use_device_port():
            abon = Abon.objects.get(dev_port__device=dev,
                                    dev_port__num=switch_port,
                                    device=dev, is_active=True)
        else:
            abon = Abon.objects.get(device=dev, is_active=True)
        if not abon.is_dynamic_ip:
            return 'User settings is not dynamic'
        if client_ip == abon.ip_address:
            return 'Ip has already attached'
        abon.attach_ip_addr(client_ip, strict=False)
        if abon.is_access():
            r = abon.nas_sync_self()
            return r if r else None
        else:
            return 'User %s is not access to service' % abon.username
    except Abon.DoesNotExist:
        return "User with device with mac '%s' does not exist" % switch_mac
    except Device.DoesNotExist:
        return 'Device with mac %s not found' % switch_mac
    except Port.DoesNotExist:
        return 'Port %(switch_port)d on device with mac %(switch_mac)s does not exist' % {
            'switch_port': int(switch_port),
            'switch_mac': switch_mac
        }
    except MultipleObjectsReturned as e:
        return 'MultipleObjectsReturned:' + ' '.join(
            (type(e), e, str(switch_port))
        )


def dhcp_expiry(client_ip: str) -> Optional[str]:
    abon = Abon.objects.filter(
        ip_address=client_ip, is_active=True
    ).exclude(current_tariff=None).first()
    if abon is None:
        return "Subscriber with ip %s does not exist" % client_ip
    else:
        is_freed = abon.free_ip_addr()
        if is_freed:
            abon.nas_sync_self()


dhcp_release = dhcp_expiry
