from kombu.exceptions import OperationalError

from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from djing.tasks import send_email_notify # , multicast_email_notify
from messenger.tasks import multicast_viber_notify, send_viber_message


# Maked compatible


class TaskException(Exception):
    pass


def handle(task, author, recipients):
    profile_ids = []
    for recipient in recipients:
        if not recipient.flags.notify_task:
            continue
        # If signal to myself then quietly
        if author == recipient:
            return
        profile_ids.append(recipient.pk)

    task_status = _('Task')

    # If task completed or failed
    if task.state in (1, 2):
        task_status = _('Task completed')

    fulltext = render_to_string('taskapp/notification.html', {
        'task': task,
        'abon': task.abon,
        'task_status': task_status
    })

    try:
        if task.state in (1, 2):
            # If task completed or failed than send one message to author
            send_email_notify.delay(fulltext, author.pk)
            send_viber_message.delay(None, author.pk, fulltext)
        else:
            # multicast_email_notify.delay(fulltext, profile_ids)
            multicast_viber_notify.delay(None, profile_ids, fulltext)
    except OperationalError as e:
        raise TaskException(e)
