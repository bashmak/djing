from django.shortcuts import resolve_url
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator

from groupapp.models import Group


class PotentialSubscriber(models.Model):
    fio = models.CharField(_('fio'), max_length=256)
    telephone = models.CharField(
        max_length=16,
        verbose_name=_('Telephone'),
        blank=True,
        null=True,
        validators=(RegexValidator(
            getattr(settings, 'TELEPHONE_REGEXP', r'^(\+[7893]\d{10,11})?$')
        ),)
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        blank=True, null=True,
        verbose_name=_('User group')
    )
    town = models.CharField(
        _('Town'),
        help_text=_('Town, if group does not already exist'),
        max_length=127, blank=True, null=True
    )
    street = models.CharField(_('Street'), max_length=127, blank=True, null=True)
    house = models.CharField(
        _('House'),
        max_length=12,
        null=True,
        blank=True
    )
    description = models.TextField(
        _('Comment'),
        null=True,
        blank=True
    )
    make_data = models.DateTimeField(_('Create date'), auto_now_add=True)
    deadline = models.DateField(
        _('Deadline connection'),
        help_text=_('Date when connection must be finished'),
        blank=True, null=True
    )

    def get_absolute_url(self):
        return resolve_url('new_customers:user', uid=self.pk)

    class Meta:
        db_table = 'new_customers'
        verbose_name = _('Potential customer')
        verbose_name_plural = _('Potential customers')
        ordering = '-id',
