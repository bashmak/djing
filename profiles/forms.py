# -*- coding: utf-8 -*-
from guardian.forms import UserObjectPermissionsForm
from guardian.shortcuts import assign_perm, remove_perm
from django import forms
from .models import UserProfile


class MyUserObjectPermissionsForm(UserObjectPermissionsForm):
    def __init__(self, *args, **kwargs):
        super(MyUserObjectPermissionsForm, self).__init__(*args, **kwargs)
        self.fields['permissions'].widget.attrs.update({
            'size': 15
        })

    def save_obj_perms(self):
        """
        Saves selected object permissions by creating new ones and removing
        those which were not selected but already exists.

        Should be called *after* form is validated.
        """
        perms = set(self.cleaned_data[self.get_obj_perms_field_name()])
        model_perms = set((c[0] for c in self.get_obj_perms_field_choices()))
        init_perms = set(self.get_obj_perms_field_initial())

        to_remove = (model_perms - perms) & init_perms
        for perm in to_remove:
            remove_perm(perm, self.user, self.obj)

        for perm in perms - init_perms:
            assign_perm(perm, self.user, self.obj)


class AvatarChangeForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('avatar',)


class UserPermissionsForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(UserPermissionsForm, self).__init__(*args, **kwargs)
        self.fields['user_permissions'].widget.attrs.update({
            'size': 35
        })

    class Meta:
        model = UserProfile
        fields = ('user_permissions', 'is_superuser')


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        exclude = ('avatar', 'password', 'groups', 'user_permissions',
                   'responsibility_groups', 'is_admin', 'is_superuser', 'last_login')
