import logging
from _socket import gaierror
from smtplib import SMTPException
from typing import Iterable

from profiles.models import UserProfile
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from celery import shared_task


@shared_task
def send_email_notify(msg_text: str, account_id: int):
    try:
        account = UserProfile.objects.get(pk=account_id)
        target_email = account.email
        text_content = strip_tags(msg_text)

        msg = EmailMultiAlternatives(
            subject=getattr(settings, 'COMPANY_NAME', 'Djing notify'),
            body=text_content,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL'),
            to=(target_email,)
        )
        msg.attach_alternative(msg_text, 'text/html')
        msg.send()
    except SMTPException as e:
        logging.error('SMTPException: %s' % e)
    except gaierror as e:
        logging.error('Socket error: %s' % e)
    except UserProfile.DoesNotExist:
        logging.error('UserProfile with pk=%d not found' % account_id)


@shared_task
def multicast_email_notify(msg_text: str, account_ids: Iterable):
    text_content = strip_tags(msg_text)
    targets = [usr.email for usr in UserProfile.objects.filter(pk__in=account_ids).only('email').iterator()]
    try:
        msg = EmailMultiAlternatives(
            subject=getattr(settings, 'COMPANY_NAME', 'Djing notify'),
            body=text_content,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL'),
            to=targets
        )
        msg.attach_alternative(msg_text, 'text/html')
        msg.send()
    except SMTPException as e:
        logging.error('SMTPException: %s' % e)
    except gaierror as e:
        logging.error('Socket error: %s' % e)
