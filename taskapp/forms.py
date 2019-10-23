from django.utils.translation import ugettext as _
from django import forms
from .models import Task, ExtraComment, delta_add_days
from profiles.models import UserProfile
from taskapp.handle import TaskException


class TaskFrm(forms.ModelForm):
    def __init__(self, initial_abon=None, *args, **kwargs):
        kwargs.update({'initial': {
            'out_date': delta_add_days().strftime("%Y-%m-%d")
        }})
        super(TaskFrm, self).__init__(*args, **kwargs)
        self.fields['recipients'].queryset = UserProfile.objects.filter(is_admin=True, is_active=True)

        if initial_abon is not None:
            # fetch profiles that has been attached on group of selected subscriber
            profile_ids = UserProfile.objects.get_profiles_by_group(initial_abon.group.pk).values_list('pk')
            if len(profile_ids) > 0:
                self.fields['recipients'].initial = [pi[0] for pi in profile_ids]
            else:
                raise TaskException(_('No responsible employee for the users group'))

    def save(self, commit=True):
        abon = self.data.get('abon') or None
        if abon is None:
            raise TaskException(_('You must select the subscriber'))
        return super(TaskFrm, self).save(commit)

    class Meta:
        model = Task
        exclude = ('time_of_create', 'author', 'device')
        widgets = {
            'descr': forms.TextInput(attrs={
                'placeholder': _('Short description'),
                'autofocus': ''
            }),
            'recipients': forms.SelectMultiple(attrs={
                'size': 10
            }),
            'out_date': forms.DateInput(attrs={'type': 'date'})
        }


class ExtraCommentForm(forms.ModelForm):
    def make_save(self, author, task: Task):
        comment = super(ExtraCommentForm, self).save(commit=False)
        comment.author = author
        comment.task = task
        comment.save()
        return comment

    def save(self, commit=True):
        raise Exception('You must use ExtraCommentForm.make_save() method')

    class Meta:
        model = ExtraComment
        fields = ('text',)
