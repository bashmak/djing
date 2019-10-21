from datetime import datetime, timedelta, date, time
import math

from django.db import models, connection, ProgrammingError
from django.utils.timezone import now
from .fields import UnixDateTimeField


def get_dates():
    tables = connection.introspection.table_names()
    tables = (t.replace('flowstat_', '') for t in tables if t.startswith('flowstat_'))
    return tuple(datetime.strptime(t, '%d%m%Y').date() for t in tables)


class StatManager(models.Manager):
    def chart(self, user, count_of_parts=12, want_date=date.today()):
        def byte_to_mbit(x):
            return ((x / 60) * 8) / 2 ** 20

        def split_list(lst, chunk_count):
            chunk_size = len(lst) // chunk_count
            if chunk_size == 0:
                chunk_size = 1
            return tuple(lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size))

        def avarage(elements):
            return sum(elements) / len(elements)

        try:
            charts_data = self.filter(abon=user)
            charts_times = tuple(cd.cur_time.timestamp() * 1000 for cd in charts_data)
            charts_octets = tuple(cd.octets for cd in charts_data)
            if len(charts_octets) > 0 and len(charts_octets) == len(charts_times):
                charts_octets = split_list(charts_octets, count_of_parts)
                charts_octets = (byte_to_mbit(avarage(c)) for c in charts_octets)

                charts_times = split_list(charts_times, count_of_parts)
                charts_times = tuple(avarage(t) for t in charts_times)

                charts_data = zip(charts_times, charts_octets)
                charts_data = ["{x: new Date(%d), y: %.2f}" % (cd[0], cd[1]) for cd in charts_data]
                midnight = datetime.combine(want_date, time.min)
                charts_data.append("{x:new Date(%d),y:0}" % (int(charts_times[-1:][0]) + 1))
                charts_data.append("{x:new Date(%d),y:0}" % (int((midnight + timedelta(days=1)).timestamp()) * 1000))
                return charts_data
            else:
                return
        except ProgrammingError as e:
            if "flowstat" in str(e):
                return


class StatElem(models.Model):
    cur_time = UnixDateTimeField(primary_key=True)
    abon = models.ForeignKey('abonapp.Abon', on_delete=models.CASCADE, null=True, default=None, blank=True)
    ip = models.PositiveIntegerField()
    octets = models.PositiveIntegerField(default=0)
    packets = models.PositiveIntegerField(default=0)

    objects = StatManager()

    # ReadOnly
    def save(self, *args, **kwargs):
        pass

    # ReadOnly
    def delete(self, *args, **kwargs):
        pass

    @property
    def table_name(self):
        return self._meta.db_table

    def delete_month(self):
        cursor = connection.cursor()
        table_name = self._meta.db_table
        sql = "DROP TABLE IF EXISTS %s;" % table_name
        cursor.execute(sql)

    @staticmethod
    def percentile(N, percent, key=lambda x: x):
        """
        Find the percentile of a list of values.

        @parameter N - is a list of values. Note N MUST BE already sorted.
        @parameter percent - a float value from 0.0 to 1.0.
        @parameter key - optional key function to compute value from each element of N.

        @return - the percentile of the values
        """
        if not N:
            return None
        k = (len(N) - 1) * percent
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return key(N[int(k)])
        d0 = key(N[int(f)]) * (c - k)
        d1 = key(N[int(c)]) * (k - f)
        return d0 + d1

    class Meta:
        abstract = True


def getModel(want_date=None):
    if want_date is None:
        want_date = now()
    se = StatElem
    se.Meta.db_table = 'flowstat_%s' % want_date.strftime("%d%m%Y")
    se.Meta.abstract = False
    return se


class StatCache(models.Model):
    last_time = UnixDateTimeField()
    abon = models.OneToOneField('abonapp.Abon', on_delete=models.CASCADE, primary_key=True)
    octets = models.PositiveIntegerField(default=0)
    packets = models.PositiveIntegerField(default=0)

    def is_online(self):
        return self.last_time > now() - timedelta(minutes=55)

    def is_today(self):
        return date.today() == self.last_time.date()

    def octets_to(self, to='m', bsize=1024):
        """convert octets <bytes> to megabytes, etc.
           sample code:
               print('mb= ' + str(bytesto(314575262000000, 'm')))
           sample output:
               mb= 300002347.946
           to:
        :param to: may be one of k m g t p e
        :param bsize: byte size
        """
        a = {'k': 1, 'm': 2, 'g': 3, 't': 4, 'p': 5, 'e': 6}
        r = float(self.octets)
        for i in range(a[to]):
            r = r / bsize
        return r

    class Meta:
        db_table = 'flowcache'
        db_tablespace = 'ram'
        # ordering = ('-last_time',)
