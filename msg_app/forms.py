from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Conversation, Message, MessageError
from profiles.models import UserProfile


class ConversationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(ConversationForm, self).__init__(*args, **kwargs)
        user_profile_queryset = UserProfile.objects.filter(is_admin=True, is_active=True)
        if user_profile_queryset is not None:
            self.fields['participants'].choices = [(up.pk, up.get_full_name()) for up in user_profile_queryset]

    title = forms.CharField(
        max_length=32, required=False,
        widget=forms.TextInput(attrs={'maxlength': '32'})
    )
    participants = forms.MultipleChoiceField(
        required=False,
    )

    class Meta:
        model = Conversation
        exclude = ('date_create', 'author')

    def create(self, author):
        participants = self.cleaned_data['participants']
        if not participants:
            raise MessageError(_('you must choose at least 1 participants'))
        conversation = Conversation.objects.create_conversation(
            author=author, title=self.cleaned_data['title'],
            other_participants=participants
        )
        return conversation

    # must be use create()
    def save(self, commit=True):
        # You must use ConversationForm.create() for save the form
        raise NotImplementedError


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        exclude = ('sent_at', 'author', 'conversation', 'account_status')
        widgets = {
            'text': forms.Textarea(attrs={'required': ''})
        }

    def create(self, conversation, author):
        if not isinstance(conversation, Conversation):
            raise TypeError
        if not isinstance(author, UserProfile):
            raise TypeError
        msg = conversation.new_message(
            text=self.cleaned_data['text'],
            attachment=self.cleaned_data['attachment'],
            author=author
        )
        return msg

    def save(self, commit=True):
        # You must use MessageForm.create() for save the form
        raise NotImplementedError
