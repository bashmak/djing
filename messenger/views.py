from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import HttpResponseForbidden, HttpResponse, HttpResponseNotFound
from django.shortcuts import resolve_url
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _, gettext
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, FormView, View
from django.views.generic.detail import SingleObjectMixin
from viberbot.api.messages import KeyboardMessage, ContactMessage
from viberbot.api.user_profile import UserProfile as ViberUserProfile
from viberbot.api.viber_requests import (
    ViberMessageRequest, ViberSubscribedRequest,
    ViberFailedRequest, ViberUnsubscribedRequest
)

from profiles.models import UserProfile
from djing.lib.mixins import LoginAdminPermissionMixin, LoginAdminMixin
from messenger import forms, models

from messenger.models import ViberMessage, ViberSubscriber


class MessengerListView(LoginAdminPermissionMixin, ListView):
    model = models.Messenger
    permission_required = 'messenger.view_messenger'


class AddMessengerCreateView(LoginAdminMixin, FormView):
    template_name = 'messenger/add_messenger.html'
    form_class = forms.MessengerForm

    def form_valid(self, form):
        bot_type = form.cleaned_data.get('bot_type')
        if isinstance(bot_type, int) and bot_type > 0:
            if bot_type == 1:
                self.success_url = resolve_url('messenger:add_viber_messenger')
                return super().form_valid(form)
        messages.info(self.request, _('Unexpected bot type'))
        self.success_url = resolve_url('messenger:messengers_list')
        return super().form_valid(form)


class AddMessengerViberCreateView(LoginAdminMixin, PermissionRequiredMixin, CreateView):
    model = models.ViberMessenger
    form_class = forms.MessengerViberForm
    permission_required = 'messenger.add_vibermessenger'
    success_url = reverse_lazy('messenger:messengers_list')

    def form_valid(self, form):
        r = super().form_valid(form)
        messages.success(self.request, _('New viber messenger successfully created'))
        return r


class UpdateViberMessengerUpdateView(LoginAdminPermissionMixin, UpdateView):
    model = models.ViberMessenger
    form_class = forms.MessengerViberForm
    permission_required = 'messenger.change_vibermessenger'

    def form_valid(self, form):
        r = super().form_valid(form)
        messages.success(self.request, _('Viber messenger successfully updated'))
        return r


class RemoveViberMessengerDeleteView(LoginAdminPermissionMixin, DeleteView):
    model = models.ViberMessenger
    permission_required = 'messenger.delete_vibermessenger'
    success_url = reverse_lazy('messenger:messengers_list')

    def delete(self, request, *args, **kwargs):
        r = super().delete(request, *args, **kwargs)
        messages.success(request, _('Viber messenger successfully deleted'))
        return r


class ListenViberView(SingleObjectMixin, View):
    http_method_names = 'post',
    model = models.ViberMessenger

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if not obj:
            return HttpResponseNotFound()
        self.object = obj
        viber = obj.get_viber()
        if not viber.verify_signature(request.body, request.META.get('HTTP_X_VIBER_CONTENT_SIGNATURE')):
            return HttpResponseForbidden()
        vr = viber.parse_request(request.body)
        if isinstance(vr, ViberMessageRequest):
            in_msg = vr.message
            if isinstance(in_msg, ContactMessage):
                self.inbox_contact(in_msg, vr.sender)
            subscriber, created = self.make_subscriber(vr.sender)
            if not created:
                ViberMessage.objects.create(
                    msg=vr.message,
                    sender=vr.sender.id,
                    messenger=obj,
                    subscriber=subscriber
                )
        elif isinstance(vr, ViberSubscribedRequest):
            self.make_subscriber(vr.user)
        elif isinstance(vr, ViberFailedRequest):
            print("client failed receiving message. failure: {0}".format(vr))
        elif isinstance(vr, ViberUnsubscribedRequest):
            ViberSubscriber.objects.filter(
                uid=vr.user_id
            ).delete()
        return HttpResponse(status=200)

    def make_subscriber(self, viber_user_profile: ViberUserProfile):
        subscriber, created = ViberSubscriber.objects.get_or_create(
            uid=viber_user_profile.id,
            defaults={
                'name': viber_user_profile.name,
                'avatar': viber_user_profile.avatar
            }
        )
        if created and hasattr(self, 'object'):
            msg = KeyboardMessage(keyboard={
                'Type': 'keyboard',
                'DefaultHeight': True,
                'Buttons': ({
                    'ActionType': 'share-phone',
                    'ActionBody': 'reply to me',
                    "Text": gettext('My telephone number'),
                    "TextSize": "medium"
                },)
            }, min_api_version=3)
            viber = self.object
            viber.send_message_to_id(viber_user_profile.id, msg)
        return subscriber, created

    def inbox_contact(self, msg, sender: ViberUserProfile):
        tel = msg.contact.phone_number
        accs = UserProfile.objects.filter(telephone__icontains=tel)
        viber = self.object
        if accs.exists():
            first_acc = accs.first()
            subs = ViberSubscriber.objects.filter(uid=sender.id)
            subs_len = subs.count()
            if subs_len > 0:
                first_sub = subs.first()
                if subs_len > 1:
                    ViberSubscriber.objects.exclude(pk=first_sub.pk).delete()
                first_sub.account = first_acc
                first_sub.name = first_acc.get_full_name()
                first_sub.save(update_fields=('account', 'name'))
                viber.send_message_to_acc(first_acc, gettext(
                    'Your account is attached. Now you will be receive notifications from billing'
                ))
        else:
            viber.send_message_to_id(sender.id, gettext(
                'Telephone not found, please specify telephone number in account in billing'
            ))


class SetWebhook(LoginAdminMixin, SingleObjectMixin, View):
    http_method_names = 'get',
    model = models.ViberMessenger

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        if not obj:
            return HttpResponseNotFound
        obj.send_webhook()
        return HttpResponse(b'ok', status=200)


class SubscribersListView(LoginAdminMixin, ListView):
    model = models.ViberSubscriber

    def get_context_data(self, **kwargs):
        context = {
            'messanger_slug': self.kwargs.get('slug')
        }
        context.update(kwargs)
        return super().get_context_data(**context)
