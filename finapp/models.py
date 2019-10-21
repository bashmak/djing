from datetime import datetime
from django.db import models, connection
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from encrypted_model_fields.fields import EncryptedCharField

from abonapp.models import Abon


# Maked compatible

class AllTimePayLogManager(models.Manager):
    @staticmethod
    def by_days():
        cur = connection.cursor()
        cur.execute(
            'SELECT SUM(summ) AS alsum, '
            'DATE_FORMAT(date_add, "%Y-%m-%d") AS pay_date '
            'FROM  all_time_pay_log '
            'GROUP BY DATE_FORMAT(date_add, "%Y-%m-%d")'
        )
        while True:
            r = cur.fetchone()
            if r is None:
                break
            summ, dat = r
            yield {
                'summ': summ,
                'pay_date': datetime.strptime(dat, '%Y-%m-%d')
            }


class PayAllTimeGateway(models.Model):
    title = models.CharField(_('Title'), max_length=64)
    secret = EncryptedCharField(verbose_name=_('Secret'), max_length=64)
    service_id = models.CharField(_('Service id'), max_length=64)
    slug = models.SlugField(_('Slug'), max_length=32,
                            unique=True, allow_unicode=False)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('finapp:edit_pay_gw', self.slug)

    class Meta:
        db_table = 'pay_all_time_gateways'
        verbose_name = _('All time gateway')
        ordering = 'title',


# Log for pay system "AllTime"
class AllTimePayLog(models.Model):
    abon = models.ForeignKey(
        Abon,
        on_delete=models.SET_DEFAULT,
        blank=True,
        null=True,
        default=None,
        db_column='customer_id'
    )
    pay_id = models.CharField(
        max_length=36,
        unique=True,
        primary_key=True
    )
    date_add = models.DateTimeField(auto_now_add=True)
    summ = models.FloatField(_('Cost'), default=0.0, db_column='sum')
    trade_point = models.CharField(
        _('Trade point'),
        max_length=20,
        default=None,
        null=True,
        blank=True
    )
    receipt_num = models.BigIntegerField(_('Receipt number'), default=0)
    pay_gw = models.ForeignKey(PayAllTimeGateway,
                               verbose_name=_('Pay gateway'),
                               on_delete=models.CASCADE)

    objects = AllTimePayLogManager()

    def __str__(self):
        return self.pay_id

    class Meta:
        db_table = 'all_time_pay_log'
        ordering = ('-date_add',)
