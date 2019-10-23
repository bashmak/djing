from typing import Optional, Iterable

from celery import shared_task

from profiles.models import UserProfile
from messenger.models import ViberMessenger


@shared_task
def send_viber_message(messenger_id: Optional[int], account_id: int, message_text: str) -> Optional[str]:
    """
    Send text message via viber
    :param messenger_id: Primary key UID for messanger.ViberMessenger
    :param account_id: User id from profiles.UserProfile
    :param message_text:
    :return: Optional text for log
    """
    if not message_text:
        return 'ERROR: empty message text'
    try:
        sp = UserProfile.objects.get(pk=account_id)
        if messenger_id is None:
            for vm in ViberMessenger.objects.all().iterator():
                vm.send_message_to_acc(sp, message_text)
        else:
            vm = ViberMessenger.objects.get(pk=messenger_id)
            vm.send_message_to_acc(sp, message_text)
    except ViberMessenger.DoesNotExist:
        return 'ERROR: Viber messanger with id=%d not found' % messenger_id
    except UserProfile.DoesNotExist:
        return 'ERROR: profiles.UserProfile with pk=%d does not exist' % account_id


@shared_task
def multicast_viber_notify(messenger_id: Optional[int], account_id_list: Iterable[int], message_text: str):
    """
    Send multiple message via Viber to several addresses
    :param messenger_id: Primary key UID for messanger.ViberMessenger
    :param account_id_list: list of account ids from profiles.UserProfile
    :param message_text:
    :return: Optional text for log
    """
    if not message_text:
        return 'ERROR: empty message text'
    account_id_list = tuple(account_id_list)
    recipients = UserProfile.objects.filter(pk__in=account_id_list)
    if not recipients.exists():
        return 'No recipients found from ids: %s' % ','.join(str(i) for i in account_id_list)
    if messenger_id is None:
        for vm in ViberMessenger.objects.all().iterator():
            vm.send_message_to_accs(recipients, message_text)
    else:
        vm = ViberMessenger.objects.filter(pk=messenger_id).first()
        if vm is None:
            return 'ERROR ViberMessenger with pk=%d does not exist' % messenger_id
        vm.send_message_to_accs(recipients, message_text)
