# coding=utf-8
from datetime import timedelta
from django.db import models
from django.conf import settings
from django.shortcuts import resolve_url
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from abonapp.models import Abon
from .handle import handle as task_handle

# Maked compatible

TASK_PRIORITIES = (
    # ('A', _('Higher')),
    # ('C', _('Average')),
    # ('E', _('Low'))
    (2, _('Higher')),
    (1, _('Average')),
    (0, _('Low')),
)

TASK_STATES = (
    # ('S', _('New')),
    # ('C', _('Confused')),
    # ('F', _('Completed'))
    (0, _('New')),
    (1, _('Confused')),
    (2, _('Completed'))
)

TASK_TYPES = (
    # ('na', _('not chosen')),
    # ('ic', _('ip conflict')),
    # ('yt', _('yellow triangle')),
    # ('rc', _('red cross')),
    # ('ls', _('weak speed')),
    # ('cf', _('cable break')),
    # ('cn', _('connection')),
    # ('pf', _('periodic disappearance')),
    # ('cr', _('router setup')),
    # ('co', _('configure onu')),
    # ('fc', _('crimp cable')),
    # ('ni', _('Internet crash')),
    # ('ot', _('other'))
    (0, _('not chosen')),
    (1, _('ip conflict')),
    (2, _('yellow triangle')),
    (3, _('red cross')),
    (4, _('weak speed')),
    (5, _('cable break')),
    (6, _('connection')),
    (7, _('periodic disappearance')),
    (8, _('router setup')),
    (9, _('configure onu')),
    (10, _('crimp cable')),
    (11, _('Internet crash')),
    (12, _('other'))
)


class ChangeLog(models.Model):
    task = models.ForeignKey('Task', on_delete=models.CASCADE)
    ACT_CHOICES = (
        # ('e', _('Change task')),
        # ('c', _('Create task')),
        # ('d', _('Delete task')),
        # ('f', _('Completing tasks')),
        # ('b', _('The task failed'))
        (1, _('Change task')),
        (2, _('Create task')),
        (3, _('Delete task')),
        (4, _('Completing tasks')),
        (5, _('The task failed'))
    )
    act_type = models.PositiveSmallIntegerField(choices=ACT_CHOICES)
    when = models.DateTimeField(auto_now_add=True)
    who = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE, related_name='+'
    )

    def __str__(self):
        return self.get_act_type_display()

    class Meta:
        db_table = 'task_change_log'


def delta_add_days():
    return timezone.now() + timedelta(days=3)


class Task(models.Model):
    descr = models.CharField(
        _('Description'), max_length=128,
        null=True, blank=True
    )
    recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name=_('Recipients'),
        related_name='them_task'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='+',
        on_delete=models.SET_NULL, null=True,
        blank=True, verbose_name=_('Task author')
    )
    priority = models.PositiveSmallIntegerField(
        _('A priority'),
        choices=TASK_PRIORITIES, default=TASK_PRIORITIES[2][0]
    )
    out_date = models.DateField(
        _('Reality'), null=True,
        blank=True, default=delta_add_days
    )
    time_of_create = models.DateTimeField(
        _('Date of create'), auto_now_add=True
    )
    task_state = models.PositiveSmallIntegerField(
        _('Condition'), choices=TASK_STATES,
        default=TASK_STATES[0][0]
    )
    # attachment = models.ImageField(
    #     _('Attached image'), upload_to='task_attachments/%Y.%m.%d',
    #     blank=True, null=True
    # )
    mode = models.PositiveSmallIntegerField(
        _('The nature of the damage'),
        choices=TASK_TYPES, default=0
    )
    abon = models.ForeignKey(
        Abon, on_delete=models.CASCADE, null=True,
        blank=True, verbose_name=_('Subscriber'),
        db_column='customer_id'
    )

    class Meta:
        db_table = 'task'
        ordering = ('-id',)
        permissions = (
            ('can_viewall', _('Access to all tasks')),
            ('can_remind', _('Reminders of tasks'))
        )

    def finish(self, current_user):
        self.task_state = 2  # Finished
        self.out_date = timezone.now()  # End time
        ChangeLog.objects.create(
            task=self,
            act_type=4,
            who=current_user
        )
        self.save(update_fields=('task_state', 'out_date'))

    def do_fail(self, current_user):
        self.task_state = 1  # Crashed
        ChangeLog.objects.create(
            task=self,
            act_type=5,
            who=current_user
        )
        self.save(update_fields=('task_state',))

    def send_notification(self):
        task_handle(
           self, self.author,
           self.recipients.filter(is_active=True)
        )

    def is_relevant(self):
        if self.out_date:
            return self.out_date < timezone.now().date() or self.task_state == 2
        return False


class ExtraComment(models.Model):
    text = models.TextField(_('Text of comment'))
    task = models.ForeignKey(
        Task, verbose_name=_('Owner task'),
        on_delete=models.CASCADE
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('Author'),
        on_delete=models.CASCADE
    )
    date_create = models.DateTimeField(_('Time of create'), auto_now_add=True)

    def __str__(self):
        return self.text

    def get_absolute_url(self):
        return resolve_url('tasks:edit', self.task.pk)

    class Meta:
        db_table = 'task_extra_comments'
        verbose_name = _('Extra comment')
        verbose_name_plural = _('Extra comments')
        ordering = ('-date_create',)
