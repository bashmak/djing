from typing import Union
from datetime import datetime, date
from django import template

register = template.Library()


@register.simple_tag
def is_today(time: datetime):
    if type(time) is not datetime:
        raise TypeError
    now = datetime.now()
    return now.day == time.day


@register.simple_tag
def is_yesterday(time: datetime):
    if type(time) is not datetime:
        raise TypeError
    now = datetime.now()
    return now.day - 1 == time.day


@register.filter
def is_current_year(time: Union[datetime, date]):
    if not isinstance(time, (datetime, date)):
        raise TypeError
    now = datetime.now()
    return now.year == time.year
