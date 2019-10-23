from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404, resolve_url
from django.contrib import messages
from django.urls import NoReverseMatch
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _
from django.views.generic import ListView, UpdateView, DetailView
from django.conf import settings

from groupapp.models import Group

from .models import UserProfile, UserProfileLog
from profiles import forms
from djing.lib.decorators import only_admins
from djing.lib.mixins import OnlyAdminsMixin, LoginAdminPermissionMixin, OnlySuperUserMixin
from guardian.decorators import permission_required_or_403 as permission_required
from guardian.shortcuts import get_objects_for_user, assign_perm, remove_perm


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'

    def form_invalid(self, form):
        for msg in form.non_field_errors():
            messages.error(self.request, msg)
        return super().form_invalid(form)

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        if self.request.user.is_staff:
            return resolve_url('acc_app:setup_info')
        return resolve_url('client_side:home')


def location_login(request):
    nextl = request.GET.get('next')
    nextl = '' if nextl == 'None' or nextl is None or nextl.isspace() else nextl
    try:
        auser = authenticate(request=request, byip=None)
        if auser:
            login(request, auser)
            if nextl == 'None' or nextl is None or nextl == '':
                if request.user.is_staff:
                    return redirect('acc_app:setup_info')
                return redirect('client_side:home')
            return redirect(nextl)
        return render(request, 'accounts/login.html', {
            'next': nextl,
            'form': AuthenticationForm()
        })
    except NoReverseMatch:
        return redirect('client_side:home')


class ProfileShowDetailView(LoginRequiredMixin, OnlyAdminsMixin, DetailView):
    model = UserProfile
    pk_url_kwarg = 'uid'
    template_name = 'accounts/index.html'
    context_object_name = 'userprofile'

    def get_context_data(self, **kwargs):
        context = {
            'uid': self.kwargs.get('uid')
        }
        context.update(kwargs)
        return super(ProfileShowDetailView, self).get_context_data(**context)

    def dispatch(self, request, *args, **kwargs):
        uid = self.kwargs.get('uid')
        if uid == 0:
            return redirect('acc_app:other_profile', uid=request.user.id)
        return super(ProfileShowDetailView, self).dispatch(request, *args, **kwargs)


class AvatarUpdateView(LoginRequiredMixin, OnlyAdminsMixin, UpdateView):
    form_class = forms.AvatarChangeForm
    template_name = 'accounts/settings/ch_info.html'

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return resolve_url('acc_app:other_profile', uid=self.request.user.id)


class UpdateAccount(LoginRequiredMixin, OnlySuperUserMixin, UpdateView):
    form_class = forms.UserProfileForm
    pk_url_kwarg = 'uid'
    model = UserProfile
    template_name = 'accounts/settings/userprofile_form.html'

    def form_valid(self, form):
        r = super().form_valid(form)
        messages.success(self.request, _('Saved successfully'))
        return r

    def get_context_data(self, **kwargs):
        context = {
            'form_url': resolve_url('acc_app:edit_profile', self.object.pk)
        }
        context.update(kwargs)
        return super().get_context_data(**context)


class UpdateSelfAccount(LoginRequiredMixin, UpdateView):
    form_class = forms.UserProfileForm
    pk_url_kwarg = 'uid'
    model = UserProfile
    template_name = 'accounts/settings/userprofile_form.html'

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        r = super().form_valid(form)
        messages.success(self.request, _('Saved successfully'))
        return r

    def get_context_data(self, **kwargs):
        context = {
            'form_url': resolve_url('acc_app:setup_info')
        }
        context.update(kwargs)
        return super().get_context_data(**context)


@login_required
@only_admins
@permission_required('profiles.add_userprofile')
def create_profile(request):
    if request.method == 'POST':
        username = request.POST.get('username')

        user = UserProfile()
        user.username = username
        user.fio = request.POST.get('fio')
        user.email = request.POST.get('email')
        user.telephone = request.POST.get('telephone')
        user.is_admin = True

        passwd = request.POST.get('passwd')
        conpasswd = request.POST.get('conpasswd')
        if not passwd:
            messages.error(request, _('You forget specify a password for the new account'))

        if not conpasswd:
            messages.error(request, _('You forget to repeat a password for the new account'))

        if passwd == conpasswd:
            user_qs = UserProfile.objects.filter(username=username)[:1]
            if user_qs.count() == 0:
                user.set_password(passwd)
                user.save()
                return redirect('acc_app:accounts_list')
            else:
                messages.error(request, _('Subscriber with this name already exist'))
        else:
            messages.error(request, _('Passwords does not match, try again'))
        return render(request, 'accounts/create_acc.html', {
            'newuser': user
        })
    return render(request, 'accounts/create_acc.html')


@login_required
@only_admins
def delete_profile(request, uid: int):
    prf = get_object_or_404(UserProfile, id=uid)
    if uid != request.user.id:
        if not request.user.has_perm('acc_app.delete_userprofile', prf):
            raise PermissionDenied
    prf.delete()
    messages.success(request, _('Profile has been deleted'))
    return redirect('acc_app:accounts_list')


class AccountsListView(LoginRequiredMixin, OnlyAdminsMixin, ListView):
    http_method_names = 'get',
    paginate_by = getattr(settings, 'PAGINATION_ITEMS_PER_PAGE', 10)
    template_name = 'accounts/acc_list.html'
    context_object_name = 'users'

    def get_queryset(self):
        users = UserProfile.objects.filter(is_admin=True).exclude(pk=self.request.user.pk)
        users = get_objects_for_user(self.request.user, 'profiles.view_userprofile', users)
        return users


@login_required
def perms_object(request, uid: int):
    if not request.user.is_superuser:
        raise PermissionDenied
    userprofile = get_object_or_404(UserProfile, id=uid)
    klasses = (
        'abonapp.Abon', 'profiles.UserProfile',
        'abonapp.AbonTariff', 'abonapp.AbonStreet', 'devapp.Device',
        'abonapp.PassportInfo', 'abonapp.AdditionalTelephone', 'tariff_app.PeriodicPay',
        'groupapp.Group'
    )
    return render(request, 'accounts/perms/object/objects_types.html', {
        'userprofile': userprofile,
        'klasses': klasses
    })


@method_decorator(login_required, name='dispatch')
class PermsUpdateView(UpdateView):
    http_method_names = 'get', 'post'
    template_name = 'accounts/perms/change_global_perms.html'
    model = UserProfile
    form_class = forms.UserPermissionsForm
    pk_url_kwarg = 'uid'

    def get_success_url(self):
        return resolve_url('acc_app:setup_perms', self.userprofile.pk)

    def get_object(self, queryset=None):
        self.userprofile = get_object_or_404(UserProfile, id=self.kwargs.get('uid'))
        return super(PermsUpdateView, self).get_object(queryset=queryset)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return super(PermsUpdateView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = {
            'userprofile': self.userprofile
        }
        context.update(kwargs)
        return super(PermsUpdateView, self).get_context_data(**context)

    def form_valid(self, form):
        messages.success(self.request, _('Permissions has successfully updated'))
        return super(PermsUpdateView, self).form_valid(form)


class PermissionClassListView(LoginRequiredMixin, OnlyAdminsMixin, ListView):
    http_method_names = 'get',
    paginate_by = getattr(settings, 'PAGINATION_ITEMS_PER_PAGE', 10)
    template_name = 'accounts/perms/object/objects_of_type.html'
    context_object_name = 'objects'

    def get(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return super(PermissionClassListView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(PermissionClassListView, self).get_context_data(**kwargs)
        context['klass'] = self.kwargs.get('klass_name')
        context['klass_name'] = self.required_klass_name._meta.verbose_name
        context['userprofile'] = get_object_or_404(UserProfile, pk=self.kwargs.get('uid'))
        return context

    def get_queryset(self):
        klass_name = self.kwargs.get('klass_name')
        app_label, model_name = klass_name.split('.', 1)
        klass = apps.get_model(app_label, model_name)
        objects = klass.objects.all()
        self.required_klass_name = klass
        return objects


@login_required
@only_admins
def perms_edit(request, uid: int, klass_name, obj_id):
    if not request.user.is_superuser:
        raise PermissionDenied
    userprofile = get_object_or_404(UserProfile, pk=uid)
    app_label, model_name = klass_name.split('.', 1)
    klass = apps.get_model(app_label, model_name)
    obj = get_object_or_404(klass, pk=obj_id)

    frm = forms.MyUserObjectPermissionsForm(userprofile, obj, request.POST or None)
    if request.method == 'POST' and frm.is_valid():
        frm.save_obj_perms()
        messages.success(request, _('Permissions has successfully updated'))

    return render(request, 'accounts/perms/object/perms_edit.html', {
        'userprofile': userprofile,
        'obj': obj,
        'form': frm,
        'klass': klass_name,
        'klass_name': klass._meta.verbose_name
    })


@login_required
@only_admins
def set_abon_groups_permission(request, uid: int):
    # Only superuser can change object permissions
    if not request.user.is_superuser:
        raise PermissionDenied
    userprofile = get_object_or_404(UserProfile, pk=uid)

    picked_groups = get_objects_for_user(userprofile, 'groupapp.view_group', accept_global_perms=False)
    picked_groups = picked_groups.values_list('pk', flat=True)

    if request.method == 'POST':
        checked_groups = tuple(int(ag) for ag in request.POST.getlist('grp', default=0))
        for grp in Group.objects.all():
            if grp.pk in checked_groups and grp.pk not in picked_groups:
                assign_perm('groupapp.view_group', userprofile, obj=grp)
            elif grp.pk not in checked_groups and grp.pk in picked_groups:
                remove_perm('groupapp.view_group', userprofile, obj=grp)
        return redirect('acc_app:set_abon_groups_permission', uid)
    groups = Group.objects.only('pk', 'title')

    return render(request, 'accounts/set_abon_groups_permission.html', {
        'uid': uid,
        'userprofile': userprofile,
        'groups': groups,
        'picked_groups_ids': picked_groups
    })


class ManageResponsibilityGroups(LoginRequiredMixin, OnlyAdminsMixin, ListView):
    http_method_names = ('get', 'post')
    template_name = 'accounts/manage_responsibility_groups.html'
    context_object_name = 'groups'
    queryset = Group.objects.only('pk', 'title')

    def get_success_url(self):
        return resolve_url('acc_app:manage_responsibility_groups', self.kwargs.get('uid'))

    def dispatch(self, request, *args, **kwargs):
        uid = self.kwargs.get('uid')
        self.object = get_object_or_404(UserProfile, pk=uid)
        return super(ManageResponsibilityGroups, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ManageResponsibilityGroups, self).get_context_data(**kwargs)
        context['uid'] = self.kwargs.get('uid')
        context['userprofile'] = self.object
        context['existing_groups'] = tuple(g.get('pk') for g in self.object.responsibility_groups.only('pk').values('pk'))
        return context

    def post(self, request, *args, **kwargs):
        checked_groups = (int(ag) for ag in request.POST.getlist('grp'))
        profile = self.object
        profile.responsibility_groups.clear()
        profile.responsibility_groups.add(*checked_groups)
        messages.success(request, _('Responsibilities has been updated'))
        return HttpResponseRedirect(self.get_success_url())


class ActionListView(LoginAdminPermissionMixin, ListView):
    paginate_by = getattr(settings, 'PAGINATION_ITEMS_PER_PAGE', 10)
    template_name = 'accounts/action_log.html'
    permission_required = 'profiles.view_userprofilelog'
    model = UserProfileLog

    def get_queryset(self):
        uid = self.kwargs.get('uid')
        return UserProfileLog.objects.filter(account__id=uid)

    def get_context_data(self, **kwargs):
        context = super(ActionListView, self).get_context_data(**kwargs)
        context['uid'] = self.kwargs.get('uid')
        context['userprofile'] = UserProfile.objects.get(pk=context['uid'])
        return context
