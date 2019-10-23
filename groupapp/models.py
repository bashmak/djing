from django.utils.translation import gettext_lazy as _
from django.shortcuts import resolve_url
from django.db import models


class Group(models.Model):
    title = models.CharField(_('Title'), max_length=127, unique=True)
    code = models.CharField(_('Tech code'), blank=True, max_length=12)

    def get_absolute_url(self):
        return resolve_url('groupapp:edit', self.pk)

    class Meta:
        db_table = 'groups'
        verbose_name = _('Group')
        verbose_name_plural = _('Groups')
        ordering = ('title',)

    def __str__(self):
        return self.title
