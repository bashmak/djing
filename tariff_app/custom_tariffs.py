# -*- coding: utf-8 -*-
from datetime import timedelta, datetime

from django.utils import timezone
from django.utils.translation import gettext as _
from .base_intr import TariffBase, PeriodicPayCalcBase
from calendar import monthrange

from random import uniform


class TariffDefault(TariffBase):
    description = _('Base calculate functionality')

    def __init__(self, abon_tariff):
        # assert isinstance(abon_tariff, AbonTariff)
        self.abon_tariff = abon_tariff

    def calc_amount(self) -> float:
        """
        Базовый функционал считает стоимость пропорционально использованному времени
        :return: Пропорциональная от времени сумма за использование услуги
        """
        # сейчас
        nw = timezone.now()

        # сколько прошло с начала действия услуги
        # если времени начала нет то это начало действия, использованное время 0
        time_diff = nw - self.abon_tariff.time_start if self.abon_tariff.time_start else timedelta(0)

        # времени в этом месяце
        curr_month_time = datetime(nw.year, nw.month if nw.month == 12 else nw.month + 1, 1) - timedelta(days=1)
        curr_month_time = timedelta(days=curr_month_time.day)

        # Сколько это в процентах от всего месяца (k - коеффициент)
        k = time_diff.total_seconds() / curr_month_time.total_seconds()

        # результат - это полная стоимость тарифа умноженная на k, k < 0
        res = k * self.abon_tariff.tariff.amount

        return float(res)

    # Тут мы расчитываем конец действия услуги, завершение будет в конце месяца
    def calc_deadline(self) -> datetime:
        nw = timezone.now()
        last_day = monthrange(nw.year, nw.month)[1]
        last_month_date = datetime(year=nw.year, month=nw.month, day=last_day,
                                   hour=23, minute=59, second=59)
        return last_month_date


class TariffDp(TariffDefault):
    description = 'IS'
    # в IS снимается вся стоимость тарифа вне зависимости от времени использования

    # просто возвращаем всю стоимость тарифа
    def calc_amount(self) -> float:
        return float(self.abon_tariff.tariff.amount)


# Как в IS только не на время, а на 10 лет
class TariffCp(TariffDp):
    description = _('Private service')

    def calc_deadline(self) -> datetime:
        # делаем время окончания услуги на 10 лет вперёд
        nw = timezone.now()
        long_long_time = datetime(year=nw.year + 10, month=1, day=1,
                                  hour=23, minute=59, second=59)
        return long_long_time


# Daily service
class TariffDaily(TariffDp):
    description = _('IS Daily service')

    def calc_deadline(self):
        nw = timezone.now()
        # next day in the same time
        one_day = timedelta(days=1)
        return nw + one_day


# Первый - всегда по умолчанию
TARIFF_CHOICES = (
    # ('Df', TariffDefault),
    # ('Dp', TariffDp),
    # ('Cp', TariffCp),
    # ('Dl', TariffDaily)
    (0, TariffDefault),
    (1, TariffDp),
    (2, TariffCp),
    (3, TariffDaily)
)


class PeriodicPayCalcDefault(PeriodicPayCalcBase):
    description = _('Default periodic pay')

    def calc_amount(self, model_object) -> float:
        return model_object.amount

    def get_next_time_to_pay(self, model_object, last_time_payment) -> datetime:
        # TODO: решить какой будет расёт периодических платежей
        return datetime.now() + timedelta(days=30)


class PeriodicPayCalcCustom(PeriodicPayCalcDefault):
    description = _('Custom periodic pay')

    def calc_amount(self, model_object) -> float:
        """
        :param model_object: it is a instance of models.PeriodicPay model
        :return: float: amount for the service
        """
        return uniform(1, 10)


PERIODIC_PAY_CHOICES = (
    # ('df', PeriodicPayCalcDefault),
    # ('cs', PeriodicPayCalcCustom)
    (0, PeriodicPayCalcDefault),
    (1, PeriodicPayCalcCustom)
)
