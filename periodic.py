#!/var/www/djing/venv/bin/python
import os
from threading import Thread
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djing.settings")
django.setup()
from django.utils import timezone
from django.db import transaction
from django.db.models import Count
from abonapp.models import Abon, AbonTariff, PeriodicPayForId, AbonLog
from gw_app.nas_managers import NasNetworkError, NasFailedResult
from gw_app.models import NASModel
from djing.lib import LogicError


class NasSyncThread(Thread):
    def __init__(self, nas):
        super(NasSyncThread, self).__init__()
        self.nas = nas

    def run(self):
        try:
            tm = self.nas.get_nas_manager()
            users = Abon.objects \
                .filter(is_active=True, nas=self.nas) \
                .exclude(current_tariff=None, ip_address=None) \
                .iterator()
            tm.sync_nas(users)
        except NasNetworkError as er:
            print('NetworkTrouble:', er)
        except NASModel.DoesNotExist:
            raise NotImplementedError


def main():
    AbonTariff.objects.filter(abon=None).delete()
    now = timezone.now()
    fields = ('id', 'tariff__title', 'abon__id', 'abon__username')
    expired_services = AbonTariff.objects.exclude(abon=None).filter(
        deadline__lt=now,
        abon__autoconnect_service=False
    )

    # finishing expires services
    with transaction.atomic():
        for ex_srv in expired_services.only(*fields).values(*fields):
            log = AbonLog.objects.create(
                abon_id=ex_srv['abon__id'],
                amount=0,
                author=None,
                date=now,
                comment="Срок действия услуги '%(service_name)s' для '%(username)s' истёк" % {
                    'service_name': ex_srv['tariff__title'],
                    'username': ex_srv['abon__username']
                }
            )
            print(log)
        expired_services.delete()

    # Automatically connect new service
    for ex in AbonTariff.objects.filter(
        deadline__lt=now,
        abon__autoconnect_service=True
    ).exclude(abon=None).iterator():
        abon = ex.abon
        trf = ex.tariff
        amount = round(trf.amount, 2)
        if abon.ballance >= amount:
            # can continue service
            with transaction.atomic():
                abon.ballance -= amount
                ex.time_start = now
                ex.deadline = None  # Deadline sets automatically in signal pre_save
                ex.save(update_fields=('time_start', 'deadline'))
                abon.save(update_fields=('ballance',))
                # make log about it
                l = AbonLog.objects.create(
                    abon=abon, amount=-amount,
                    comment="Автоматическое продление услуги '%s' для %s" % (trf.title, abon)
                )
                print(l.comment)
        else:
            # finish service
            with transaction.atomic():
                ex.delete()
                l = AbonLog.objects.create(
                    abon_id=ex.abon.id,
                    amount=0,
                    author=None,
                    date=now,
                    comment="Срок действия услуги '%(service_name)s' истёк" % {
                        'service_name': ex.tariff.title
                    }
                )
                print(l.comment)

    # Post connect service
    # connect service when autoconnect is True, and user have enough money
    for ab in Abon.objects.filter(
        is_active=True,
        current_tariff=None,
        autoconnect_service=True
    ).exclude(last_connected_tariff=None).iterator():
        try:
            tariff = ab.last_connected_tariff
            if tariff is None or tariff.is_admin:
                continue
            ab.pick_tariff(
                tariff, None,
                "Автоматическое продление услуги '%s'" % tariff.title
            )
        except LogicError as e:
            print(e)

    # manage periodic pays
    ppays = PeriodicPayForId.objects.filter(next_pay__lt=now) \
        .prefetch_related('account', 'periodic_pay')
    for pay in ppays:
        pay.payment_for_service(now=now)

    # sync subscribers on GW
    threads = tuple(NasSyncThread(nas) for nas in NASModel.objects.
                    annotate(usercount=Count('abon')).
                    filter(usercount__gt=0, enabled=True))
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    try:
        main()
    except (NasNetworkError, NasFailedResult) as e:
        print("Error while sync nas:", e)
    except LogicError as e:
        print("Notice while sync nas:", e)
