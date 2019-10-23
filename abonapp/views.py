from datetime import datetime
from typing import Dict, Optional
from kombu.exceptions import OperationalError

from abonapp.tasks import customer_nas_command, customer_nas_remove
from agent.commands.dhcp import dhcp_commit, dhcp_expiry, dhcp_release
from devapp.models import Device, Port as DevPort
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import (
    HttpResponse, HttpResponseBadRequest,
    HttpResponseRedirect
)
from django.shortcuts import render, redirect, get_object_or_404, resolve_url
from django.urls import reverse_lazy

from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, UpdateView, CreateView, DeleteView, DetailView
from djing import lib
from djing.global_base_views import OrderedFilteredList, SecureApiView
from djing.lib.decorators import json_view, only_admins
from djing.lib.mixins import (
    OnlyAdminsMixin,
    LoginAdminPermissionMixin,
    LoginAdminMixin
)
from groupapp.models import Group
from guardian.decorators import \
    permission_required_or_403 as permission_required
from guardian.shortcuts import get_objects_for_user, assign_perm
from gw_app.models import NASModel
from gw_app.nas_managers import NasFailedResult, NasNetworkError
from ip_pool.models import NetworkModel
from tariff_app.models import Tariff
from taskapp.models import Task
from abonapp import forms
from abonapp import models


class PeoplesListView(LoginRequiredMixin, OnlyAdminsMixin,
                      OrderedFilteredList):
    template_name = 'abonapp/peoples.html'

    def get_queryset(self):
        street_id = lib.safe_int(self.request.GET.get('street'))
        gid = lib.safe_int(self.kwargs.get('gid'))
        peoples_list = models.Abon.objects.filter(group__pk=gid)
        if street_id > 0:
            peoples_list = peoples_list.filter(street=street_id)
        peoples_list = peoples_list.select_related(
            'group', 'street', 'current_tariff__tariff', 'statcache'
        ).only(
            'group', 'street', 'fio', 'birth_day',
            'street', 'house', 'telephone', 'ballance', 'markers',
            'username', 'is_active', 'current_tariff', 'ip_address'
        )
        ordering = self.get_ordering()
        if ordering and isinstance(ordering, str):
            ordering = (ordering,)
            peoples_list = peoples_list.order_by(*ordering)
        return peoples_list

    def get_context_data(self, **kwargs):
        gid = lib.safe_int(self.kwargs.get('gid'))
        if gid < 1:
            return HttpResponseBadRequest('group id is broken')
        group = get_object_or_404(Group, pk=gid)
        if not self.request.user.has_perm('groupapp.view_group', group):
            raise PermissionDenied

        context = super(PeoplesListView, self).get_context_data(**kwargs)

        context['streets'] = models.AbonStreet.objects.filter(
            group=gid
        ).only('name')
        context['street_id'] = lib.safe_int(self.request.GET.get('street'))
        context['group'] = group
        return context


class GroupListView(LoginRequiredMixin, OnlyAdminsMixin, OrderedFilteredList):
    context_object_name = 'groups'
    template_name = 'abonapp/group_list.html'

    def get_queryset(self):
        queryset = get_objects_for_user(
            self.request.user,
            'groupapp.view_group', klass=Group,
            use_groups=False,
            accept_global_perms=False
        )
        return queryset.annotate(usercount=Count('abon'))


class AbonCreateView(LoginRequiredMixin, OnlyAdminsMixin,
                     PermissionRequiredMixin, CreateView):
    permission_required = 'abonapp.add_abon'
    group = None
    abon = None
    form_class = forms.AbonForm
    model = models.Abon
    template_name = 'abonapp/addAbon.html'
    context_object_name = 'group'

    def dispatch(self, request, *args, **kwargs):
        group = get_object_or_404(Group, pk=self.kwargs.get('gid'))
        if not request.user.has_perm('groupapp.view_group', group):
            raise PermissionDenied
        self.group = group
        return super(AbonCreateView, self).dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {
            'group': self.group,
            'address': _('Address'),
            'is_active': False
        }

    def get_context_data(self, **kwargs):
        context = super(AbonCreateView, self).get_context_data(**kwargs)
        context['group'] = self.group
        return context

    def form_valid(self, form):
        try:
            abon = form.save()
            me = self.request.user
            assign_perm("abonapp.change_abon", me, abon)
            assign_perm("abonapp.delete_abon", me, abon)
            assign_perm("abonapp.can_buy_tariff", me, abon)
            assign_perm('abonapp.can_add_ballance', me, abon)
            me.log(self.request.META, 'cusr', '%s, "%s", %s' % (
                abon.username, abon.fio,
                abon.group.title if abon.group else ''
            ))
            messages.success(self.request, _('create abon success msg'))
            self.abon = abon
            return super(AbonCreateView, self).form_valid(form)
        except (
                IntegrityError,
                NasFailedResult,
                NasNetworkError,
                lib.LogicError
        ) as e:
            messages.error(self.request, e)
        except lib.MultipleException as errs:
            for err in errs.err_list:
                messages.error(self.request, err)
        return self.render_to_response(self.get_context_data(form=form))

    def form_invalid(self, form):
        messages.error(self.request, _('fix form errors'))
        return super(AbonCreateView, self).form_invalid(form)


class DelAbonDeleteView(LoginAdminMixin, PermissionRequiredMixin, DeleteView):
    permission_required = 'abonapp.delete_abon'
    model = models.Abon
    slug_url_kwarg = 'uname'
    slug_field = 'username'
    success_url = reverse_lazy('abonapp:group_list')
    context_object_name = 'abon'

    def get_object(self, queryset=None):
        abon = super(DelAbonDeleteView, self).get_object(queryset)
        if not self.request.user.has_perm('groupapp.view_group', abon.group):
            raise PermissionDenied
        return abon

    def delete(self, request, *args, **kwargs):
        try:
            abon = self.get_object()
            gid = abon.group.id
            if abon.current_tariff:
                abon_tariff = abon.current_tariff.tariff
                customer_nas_remove.delay(
                    customer_uid=abon.pk, ip_addr=abon.ip_address,
                    speed=(abon_tariff.speedIn, abon_tariff.speedOut),
                    is_access=abon.is_access(), nas_pk=abon.nas_id
                )
            abon.delete()
            request.user.log(request.META, 'dusr', (
                '%(uname)s, "%(fio)s", %(group)s %(street)s %(house)s' % {
                    'uname': abon.username,
                    'fio': abon.fio or '-',
                    'group': abon.group.title if abon.group else '',
                    'street': abon.street.name if abon.street else '',
                    'house': abon.house or ''
                }).strip())
            messages.success(request, _('delete abon success msg'))
            return redirect('abonapp:people_list', gid=gid)
        except (NasNetworkError, OperationalError) as e:
            messages.error(self.request, e)
        except NasFailedResult as e:
            messages.error(self.request, _("NAS says: '%s'") % e)
        except lib.MultipleException as errs:
            for err in errs.err_list:
                messages.error(self.request, err)
        return HttpResponseRedirect(self.success_url)


@login_required
@only_admins
@permission_required('abonapp.can_add_ballance')
@transaction.atomic
def abonamount(request, gid: int, uname):
    abon = get_object_or_404(models.Abon, username=uname)
    frm = None
    try:
        if request.method == 'POST':
            frm = forms.AmountMoneyForm(request.POST)
            if frm.is_valid():
                amnt = frm.cleaned_data.get('amount')
                comment = frm.cleaned_data.get('comment')
                if not comment:
                    comment = _('fill account through admin side')
                abon.add_ballance(request.user, amnt, comment=comment)
                abon.save(update_fields=('ballance',))
                messages.success(
                    request, _('Account filled successfully on %.2f') % amnt
                )
                return redirect('abonapp:abon_home', gid=gid, uname=uname)
            else:
                messages.error(request, _('I not know the account id'))
        else:
            frm = forms.AmountMoneyForm()
    except (NasNetworkError, NasFailedResult) as e:
        messages.error(request, e)
    except lib.MultipleException as errs:
        for err in errs.err_list:
            messages.error(request, err)
    return render(request, 'abonapp/modal_abonamount.html', {
        'abon': abon,
        'group_id': gid,
        'form': frm
    })


class DebtsListView(LoginAdminPermissionMixin, OrderedFilteredList):
    permission_required = 'groupapp.view_group'
    context_object_name = 'invoices'
    template_name = 'abonapp/invoiceForPayment.html'

    def get_permission_object(self):
        if not hasattr(self, 'abon'):
            abon = get_object_or_404(models.Abon, username=self.kwargs.get('uname'))
            self.abon = abon
        return self.abon.group

    def get_queryset(self):
        if not hasattr(self, 'abon'):
            abon = get_object_or_404(models.Abon, username=self.kwargs.get('uname'))
            if not hasattr(self, 'abon'):
                self.abon = abon
        return models.InvoiceForPayment.objects.filter(abon=self.abon)

    def get_context_data(self, **kwargs):
        context = super(DebtsListView, self).get_context_data(**kwargs)
        context['group'] = self.abon.group
        context['abon'] = self.abon
        return context


class AbonServices(LoginAdminMixin, DetailView):
    model = models.Abon
    slug_url_kwarg = 'uname'
    slug_field = 'username'
    template_name = 'abonapp/service.html'
    context_object_name = 'abon'

    def get_object(self, queryset=None):
        gid = self.kwargs.get('gid')
        abon = super().get_object(queryset)
        if abon.group.pk != gid:
            messages.warning(
                self.request,
                _("User group id is not matches with group in url")
            )
            return redirect('abonapp:abon_services', abon.group.pk, abon.username)
        if not self.request.user.has_perm('groupapp.view_group', abon.group):
            raise PermissionDenied
        return abon

    def get_context_data(self, **kwargs):
        abon = self.object
        periodic_pay = models.PeriodicPayForId.objects.filter(
            account=abon
        ).first()
        context = {
            'abon_tariff': abon.current_tariff,
            'group': abon.group,
            'services': Tariff.objects.get_tariffs_by_group(abon.group.pk),
            'periodic_pay': periodic_pay
        }
        context.update(kwargs)
        return super().get_context_data(**context)


class AbonHomeUpdateView(LoginAdminMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'abonapp.view_abon'
    model = models.Abon
    form_class = forms.AbonForm
    slug_field = 'username'
    slug_url_kwarg = 'uname'
    template_name = 'abonapp/editAbon.html'
    context_object_name = 'abon'
    group = None

    def dispatch(self, request, *args, **kwargs):
        try:
            return super(AbonHomeUpdateView, self).dispatch(
                request, *args,
                **kwargs
            )
        except lib.LogicError as e:
            messages.error(request, e)
        except (NasFailedResult, NasNetworkError) as e:
            messages.error(request, e)
        except lib.MultipleException as errs:
            for err in errs.err_list:
                messages.error(request, err)
        return self.render_to_response(self.get_context_data())

    def get_object(self, queryset=None):
        gid = self.kwargs.get('gid')
        self.group = get_object_or_404(Group, pk=gid)
        if not self.request.user.has_perm('groupapp.view_group', self.group):
            raise PermissionDenied
        return super(AbonHomeUpdateView, self).get_object(queryset)

    def form_valid(self, form):
        r = super(AbonHomeUpdateView, self).form_valid(form)
        abon = self.object
        try:
            customer_nas_command.delay(abon.pk, 'sync')
        except OperationalError as e:
            messages.error(self.request, str(e))
        else:
            messages.success(self.request, _('edit abon success msg'))
        return r

    def form_invalid(self, form):
        messages.warning(self.request, _('fix form errors'))
        return super(AbonHomeUpdateView, self).form_invalid(form)

    def get(self, request, *args, **kwargs):
        r = super(AbonHomeUpdateView, self).get(request, *args, **kwargs)
        abon = self.object
        if abon.device is None:
            messages.warning(request, _('User device was not found'))
        return r

    def get_initial(self):
        abon = self.object
        if self.initial:
            return self.initial
        try:
            passw = models.AbonRawPassword.objects.get(
                account=abon
            ).passw_text
            return {
                'password': passw
            }
        except models.AbonRawPassword.DoesNotExist:
            messages.warning(
                self.request,
                _('User has not have password, and cannot login')
            )
        return {'password': ''}

    def get_context_data(self, **kwargs):
        abon = self.object
        device = getattr(abon, 'device')
        context = {
            'group': self.group,
            'device': device,
            'dev_ports': DevPort.objects.filter(
                device=device) if device else None
        }
        context.update(kwargs)
        return super(AbonHomeUpdateView, self).get_context_data(**context)


@login_required
@only_admins
@permission_required('abonapp.add_invoiceforpayment')
def add_invoice(request, gid: int, uname: str):
    abon = get_object_or_404(models.Abon, username=uname)
    grp = get_object_or_404(Group, pk=gid)

    try:
        if request.method == 'POST':
            curr_amount = lib.safe_int(request.POST.get('curr_amount'))
            comment = request.POST.get('comment')

            newinv = models.InvoiceForPayment()
            newinv.abon = abon
            newinv.amount = curr_amount
            newinv.comment = comment

            if request.POST.get('status') == 'on':
                newinv.status = True

            newinv.author = request.user
            newinv.save()
            messages.success(request, _('Receipt has been created'))
            return redirect('abonapp:abon_debts', gid=gid, uname=uname)

    except (NasNetworkError, NasFailedResult) as e:
        messages.error(request, e)
    except lib.MultipleException as errs:
        for err in errs.err_list:
            messages.error(request, err)
    return render(request, 'abonapp/addInvoice.html', {
        'abon': abon,
        'invcount': models.InvoiceForPayment.objects.filter(abon=abon).count(),
        'group': grp
    })


@login_required
@only_admins
@permission_required('abonapp.can_buy_tariff')
def pick_tariff(request, gid: int, uname):
    grp = get_object_or_404(Group, pk=gid)
    abon = get_object_or_404(models.Abon, username=uname)
    tariffs = Tariff.objects.get_tariffs_by_group(grp.pk)
    try:
        if request.method == 'POST':
            trf = Tariff.objects.get(pk=request.POST.get('tariff'))
            deadline = request.POST.get('deadline')
            log_comment = _(
                "Service '%(service_name)s' "
                "has connected via admin until %(deadline)s") % {
                    'service_name': trf.title,
                    'deadline': deadline
                    }
            if deadline:
                deadline = datetime.strptime(deadline, '%Y-%m-%dT%H:%M')
            abon.pick_tariff(trf, request.user, deadline=deadline, comment=log_comment)
            customer_nas_command.delay(abon.pk, 'sync')
            messages.success(request, _('Tariff has been picked'))
            return redirect('abonapp:abon_services', gid=gid,
                            uname=abon.username)
    except (lib.LogicError, NasFailedResult, NasNetworkError, OperationalError) as e:
        messages.error(request, e)
        return redirect('abonapp:abon_services', gid=gid, uname=abon.username)
    except Tariff.DoesNotExist:
        messages.error(request, _('Tariff your picked does not exist'))
    except lib.MultipleException as errs:
        for err in errs.err_list:
            messages.error(request, err)
    except ValueError as e:
        messages.error(request, "%s: %s" % (_('fix form errors'), e))

    selected_tariff = request.GET.get('selected_tariff')
    if selected_tariff:
        selected_tariff = get_object_or_404(Tariff, pk=selected_tariff)

    return render(request, 'abonapp/buy_tariff.html', {
        'tariffs': tariffs,
        'abon': abon,
        'group': grp,
        'selected_tariff': selected_tariff
    })


@login_required
@only_admins
@permission_required('abonapp.can_complete_service')
def unsubscribe_service(request, gid: int, uname, abon_tariff_id: int):
    try:
        abon_tariff = get_object_or_404(models.AbonTariff,
                                        pk=int(abon_tariff_id))
        abon = abon_tariff.abon
        trf = abon_tariff.tariff
        customer_nas_remove.delay(
            customer_uid=abon.pk, ip_addr=abon.ip_address,
            speed=(trf.speedIn, trf.speedOut),
            is_access=abon.is_access(), nas_pk=abon.nas_id
        )
        abon_tariff.delete()
        messages.success(request, _('User has been detached from service'))
    except NasFailedResult as e:
        messages.error(request, e)
    except (NasNetworkError, OperationalError) as e:
        messages.warning(request, e)
    except lib.MultipleException as errs:
        for err in errs.err_list:
            messages.error(request, err)
    return redirect('abonapp:abon_services', gid=gid, uname=uname)


class LogListView(LoginAdminPermissionMixin, ListView):
    permission_required = 'abonapp.view_abonlog'
    paginate_by = getattr(settings, 'PAGINATION_ITEMS_PER_PAGE', 10)
    http_method_names = ('get',)
    context_object_name = 'logs'
    template_name = 'abonapp/log.html'
    model = models.AbonLog


class DebtorsListView(LoginAdminPermissionMixin, ListView):
    permission_required = 'abonapp.view_invoiceforpayment'
    paginate_by = getattr(settings, 'PAGINATION_ITEMS_PER_PAGE', 10)
    http_method_names = ('get',)
    context_object_name = 'invoices'
    template_name = 'abonapp/debtors.html'
    queryset = models.InvoiceForPayment.objects.filter(status=True)


class TaskLogListView(LoginAdminPermissionMixin, ListView):
    permission_required = 'groupapp.view_group'
    paginate_by = getattr(settings, 'PAGINATION_ITEMS_PER_PAGE', 10)
    http_method_names = ('get',)
    context_object_name = 'tasks'
    template_name = 'abonapp/task_log.html'

    def get_permission_object(self):
        if hasattr(self, 'abon'):
            return self.abon.group
        else:
            return get_object_or_404(models.Group, pk=self.kwargs.get('gid'))

    def get_queryset(self):
        abon = get_object_or_404(models.Abon,
                                 username=self.kwargs.get('uname'))
        self.abon = abon
        return Task.objects.filter(abon=abon)

    def get_context_data(self, **kwargs):
        context = super(TaskLogListView, self).get_context_data(**kwargs)
        context['group'] = self.abon.group
        context['abon'] = self.abon
        return context


class PassportUpdateView(LoginAdminPermissionMixin, UpdateView):
    permission_required = 'abonapp.view_passportinfo'
    form_class = forms.PassportForm
    model = models.PassportInfo
    template_name = 'abonapp/modal_passport_view.html'

    def get_object(self, queryset=None):
        self.abon = get_object_or_404(models.Abon,
                                      username=self.kwargs.get('uname'))
        try:
            passport_instance = models.PassportInfo.objects.get(
                abon=self.abon
            )
        except models.PassportInfo.DoesNotExist:
            passport_instance = None
        return passport_instance

    def form_valid(self, form):
        pi = form.save(commit=False)
        pi.abon = self.abon
        pi.save()
        messages.success(
            self.request,
            _('Passport information has been saved')
        )
        return super(PassportUpdateView, self).form_valid(form)

    def get_success_url(self):
        return resolve_url(
            'abonapp:abon_home',
            gid=self.kwargs.get('gid'),
            uname=self.kwargs.get('uname')
        )

    def form_invalid(self, form):
        messages.error(self.request, _('fix form errors'))
        return super(PassportUpdateView, self).form_invalid(form)

    def get_context_data(self, **kwargs):
        context = {
            'group': get_object_or_404(Group, pk=self.kwargs.get('gid')),
            'abon': self.abon
        }
        context.update(kwargs)
        return super(PassportUpdateView, self).get_context_data(**context)


class IpUpdateView(LoginAdminPermissionMixin, UpdateView):
    permission_required = 'abonapp.change_abon'
    form_class = forms.AddIpForm
    model = models.Abon
    slug_url_kwarg = 'uname'
    slug_field = 'username'
    template_name = 'abonapp/modal_ip_form.html'

    def dispatch(self, request, *args, **kwargs):
        try:
            return super(IpUpdateView, self).dispatch(request, *args, **kwargs)
        except lib.LogicError as e:
            messages.error(request, e)
        except IntegrityError as e:
            str_text = str(e)
            if 'abonent_ip_address_nas_id' in str_text and 'duplicate key value' in str_text:
                messages.error(request, _('IP address conflict'))
            else:
                messages.error(request, e)
        return self.render_to_response(self.get_context_data(**kwargs))

    def form_valid(self, form):
        r = super(IpUpdateView, self).form_valid(form)
        abon = self.object
        try:
            customer_nas_command.delay(abon.pk, 'sync')
        except OperationalError as e:
            messages.error(self.request, str(e))
        else:
            messages.success(self.request, _('Ip successfully updated'))
        return r

    def get_context_data(self, **kwargs):
        context = super(IpUpdateView, self).get_context_data(**kwargs)
        context['group'] = self.object.group
        context['abon'] = self.object
        return context


@login_required
@only_admins
def chgroup_tariff(request, gid):
    grp = get_object_or_404(Group, pk=gid)
    if not request.user.has_perm('groupapp.change_group', grp):
        raise PermissionDenied
    if request.method == 'POST':
        ma = frozenset(t.id for t in grp.tariff_set.all())
        mb = frozenset(map(int, request.POST.getlist('tr')))
        sub = ma - mb
        add = mb - ma
        grp.tariff_set.remove(*sub)
        grp.tariff_set.add(*add)
        models.Abon.objects.filter(
            group=grp,
            last_connected_tariff__in=sub
        ).update(last_connected_tariff=None)
        messages.success(request, _('Successfully saved'))
        return redirect('abonapp:ch_group_tariff', gid)
    tariffs = Tariff.objects.all()
    seleted_tariffs_id = tuple(
        pk[0] for pk in grp.tariff_set.only('pk').values_list('pk')
    )
    return render(request, 'abonapp/group_tariffs.html', {
        'group': grp,
        'seleted_tariffs': seleted_tariffs_id,
        'tariffs': tariffs
    })


@login_required
@only_admins
@permission_required('abonapp.change_abon')
def dev(request, gid: int, uname):
    abon_dev = None
    try:
        abon = models.Abon.objects.get(username=uname)
        if request.method == 'POST':
            abon.device = Device.objects.get(pk=request.POST.get('dev'))
            abon.save(update_fields=('device',))
            messages.success(request, _('Device has successfully attached'))
            return redirect('abonapp:abon_home', gid=gid, uname=uname)
        else:
            abon_dev = abon.device
    except Device.DoesNotExist:
        messages.warning(
            request,
            _('Device your selected already does not exist')
        )
    except models.Abon.DoesNotExist:
        messages.error(request, _('Abon does not exist'))
        return redirect('abonapp:people_list', gid=gid)
    return render(request, 'abonapp/modal_dev.html', {
        'devices': Device.objects.filter(group=gid),
        'dev': abon_dev,
        'gid': gid, 'uname': uname
    })


@login_required
@only_admins
@permission_required('abonapp.change_abon')
@permission_required('groupapp.view_group', (Group, 'pk', 'gid'))
def clear_dev(request, gid: int, uname):
    try:
        abon = models.Abon.objects.get(username=uname)
        abon.device = None
        abon.dev_port = None
        abon.is_dynamic_ip = False
        abon.save(update_fields=('device', 'dev_port', 'is_dynamic_ip'))
        messages.success(request, _('Device has successfully unattached'))
    except models.Abon.DoesNotExist:
        messages.error(request, _('Abon does not exist'))
        return redirect('abonapp:people_list', gid=gid)
    return redirect('abonapp:abon_home', gid=gid, uname=uname)


@login_required
@only_admins
@permission_required('abonapp.can_ping')
@json_view
def abon_ping(request, gid: int, uname):
    ip = request.GET.get('cmd_param')
    status = 1
    text = '<span class="glyphicon glyphicon-exclamation-sign"></span> %s' % _('no ping')
    abon = get_object_or_404(models.Abon, username=uname)
    try:
        if ip is None:
            raise lib.LogicError(_('Ip not passed'))

        if abon.nas is None:
            return {
                'status': 1,
                'dat': '<span class="glyphicon glyphicon-exclamation-sign">'
                       '</span> %s' % _('gateway required')
            }
        mngr = abon.nas.get_nas_manager()
        ping_result = mngr.ping(ip)
        if ping_result is None:
            return {
                'status': 1,
                'dat': text
            }
        if isinstance(ping_result, tuple):
            received, sent = ping_result
            if received == 0:
                ping_result = mngr.ping(ip, arp=True)
                if ping_result is not None and isinstance(ping_result, tuple):
                    received, sent = ping_result
                else:
                    return {
                        'status': 1,
                        'dat': text
                    }
            loses_percent = (
                received / sent if sent != 0 else 1
            )
            ping_result = {'return': received, 'all': sent}
            if loses_percent > 1.0:
                text = '<span class="glyphicon glyphicon-exclamation-sign"></span> %s' % _(
                    'IP Conflict! %(return)d/%(all)d results'
                ) % ping_result
            elif loses_percent > 0.5:
                text = '<span class="glyphicon glyphicon-ok"></span> %s' % _(
                    'ok ping, %(return)d/%(all)d loses'
                ) % ping_result
                status = 0
            else:
                text = '<span class="glyphicon glyphicon-exclamation-sign"></span> %s' % _(
                    'no ping, %(return)d/%(all)d loses'
                ) % ping_result

    except (NasFailedResult, lib.LogicError) as e:
        text = str(e)
    except NasNetworkError as e:
        text = str(e)

    return {
        'status': status,
        'dat': text
    }


@login_required
@only_admins
@json_view
def set_auto_continue_service(request, gid: int, uname):
    checked = request.GET.get('checked')
    checked = checked == 'true'
    abon = get_object_or_404(models.Abon, username=uname)
    abon.autoconnect_service = checked
    abon.save(update_fields=('autoconnect_service',))
    return {
        'status': 0
    }


@login_required
@only_admins
def vcards(r):
    users = models.Abon.objects.exclude(group=None).select_related(
        'group',
        'street'
    ).only(
        'username', 'fio', 'group__title', 'telephone',
        'street__name', 'house'
    )
    additional_tels = models.AdditionalTelephone.objects.select_related(
        'abon',
        'abon__group',
        'abon__street'
    )
    response = HttpResponse(content_type='text/x-vcard')
    response['Content-Disposition'] = 'attachment; filename="contacts.vcard"'
    tmpl = ("BEGIN:VCARD\r\n"
            "VERSION:4.0\r\n"
            "FN:%(uname)s. %(group_name)s, %(street)s %(house)s\r\n"
            "IMPP:sip:%(abon_telephone)s@dial.lo\r\n"
            "END:VCARD\r\n")

    def _make_vcard():
        for ab in users.iterator():
            tel = ab.telephone
            if tel:
                yield tmpl % {
                    'uname': ab.get_full_name(),
                    'group_name': ab.group.title,
                    'street': ab.street.name if ab.street else '',
                    'house': ab.house,
                    'abon_telephone': tel
                }
        if not additional_tels.exists():
            return
        for add_tel in additional_tels.iterator():
            abon = add_tel.abon
            yield tmpl % {
                'uname': "%s (%s)" % (
                    add_tel.owner_name, abon.get_full_name()),
                'group_name': abon.group.title,
                'abon_telephone': add_tel.telephone,
                'street': abon.street.name if abon.street else '',
                'house': abon.house
            }

    response.content = _make_vcard()
    return response


@login_required
@only_admins
@permission_required('abonapp.change_abon')
def save_user_dev_port(request, gid: int, uname):
    if request.method != 'POST':
        messages.error(request, _('Method is not POST'))
        return redirect('abonapp:abon_home', gid, uname)
    user_port = lib.safe_int(request.POST.get('user_port'))
    is_dynamic_ip = request.POST.get('is_dynamic_ip')
    is_dynamic_ip = is_dynamic_ip == 'on'
    try:
        abon = models.Abon.objects.get(username=uname)
        if user_port == 0:
            port = None
        else:
            port = DevPort.objects.get(pk=user_port)
            if abon.device is not None:
                try:
                    other_abon = models.Abon.objects.get(
                        device=abon.device,
                        dev_port=port
                    )
                    if other_abon != abon:
                        user_url = resolve_url(
                            'abonapp:abon_home',
                            other_abon.group.id,
                            other_abon.username
                        )
                        messages.error(
                            request, _("<a href='%(user_url)s'>%(user_name)s</a> already pinned to this port on this device") % {
                                'user_url': user_url,
                                'user_name': other_abon.get_full_name()
                            }
                        )
                        return redirect('abonapp:abon_home', gid, uname)
                except models.Abon.DoesNotExist:
                    pass
                except models.Abon.MultipleObjectsReturned:
                    messages.error(request,
                                   _('Multiple users on the same device port'))
                    return redirect('devapp:view', abon.device.group.pk,
                                    abon.device.pk)

        abon.dev_port = port
        if abon.is_dynamic_ip != is_dynamic_ip:
            abon.is_dynamic_ip = is_dynamic_ip
            abon.save(update_fields=('dev_port', 'is_dynamic_ip'))
        else:
            abon.save(update_fields=('dev_port',))
        messages.success(request, _('User port has been saved'))
    except DevPort.DoesNotExist:
        messages.error(request, _('Selected port does not exist'))
    except models.Abon.DoesNotExist:
        messages.error(request, _('User does not exist'))
    return redirect('abonapp:abon_home', gid, uname)


@login_required
@only_admins
@permission_required('abonapp.add_abonstreet')
@permission_required('groupapp.view_group', (Group, 'pk', 'gid'))
def street_add(request, gid):
    if request.method == 'POST':
        frm = forms.AbonStreetForm(request.POST)
        if frm.is_valid():
            frm.save()
            messages.success(request, _('Street successfully saved'))
            return redirect('abonapp:people_list', gid)
        else:
            messages.error(request, _('fix form errors'))
    else:
        frm = forms.AbonStreetForm(initial={'group': gid})
    return render(request, 'abonapp/modal_addstreet.html', {
        'form': frm,
        'gid': gid
    })


@login_required
@only_admins
@permission_required('abonapp.change_abonstreet')
@permission_required('groupapp.view_group', (Group, 'pk', 'gid'))
def street_edit(request, gid):
    try:
        if request.method == 'POST':
            for sid, sname in zip(request.POST.getlist('sid'),
                                  request.POST.getlist('sname')):
                street = models.AbonStreet.objects.get(pk=sid)
                street.name = sname
                street.save()
            messages.success(request, _('Streets has been saved'))
        else:
            return render(request, 'abonapp/modal_editstreet.html', {
                'gid': gid,
                'streets': models.AbonStreet.objects.filter(group=gid)
            })

    except models.AbonStreet.DoesNotExist:
        messages.error(request, _('One of these streets has not been found'))

    return redirect('abonapp:people_list', gid)


@login_required
@only_admins
@permission_required('abonapp.delete_abonstreet')
@permission_required('groupapp.view_group', (Group, 'pk', 'gid'))
def street_del(request, gid: int, sid: int):
    try:
        models.AbonStreet.objects.get(pk=sid, group=gid).delete()
        messages.success(request, _('The street successfully deleted'))
    except models.AbonStreet.DoesNotExist:
        messages.error(request, _('The street has not been found'))
    return redirect('abonapp:people_list', gid)


@login_required
@only_admins
@permission_required('groupapp.view_group', (Group, 'pk', 'gid'))
def active_nets(request, gid):
    nets = NetworkModel.objects.filter(groups__id=gid)
    return render(request, 'abonapp/modal_current_networks.html', {
        'networks': nets
    })


@login_required
@only_admins
@permission_required('abonapp.view_additionaltelephones')
@permission_required('groupapp.view_group', (Group, 'pk', 'gid'))
def tels(request, gid: int, uname):
    abon = get_object_or_404(models.Abon, username=uname)
    telephones = abon.additional_telephones.all()
    return render(request, 'abonapp/modal_additional_telephones.html', {
        'telephones': telephones,
        'gid': gid,
        'uname': uname
    })


@login_required
@only_admins
@permission_required('abonapp.add_additionaltelephone')
def tel_add(request, gid: int, uname):
    if request.method == 'POST':
        frm = forms.AdditionalTelephoneForm(request.POST)
        if frm.is_valid():
            new_tel = frm.save(commit=False)
            abon = get_object_or_404(models.Abon, username=uname)
            new_tel.abon = abon
            new_tel.save()
            messages.success(request, _('New telephone has been saved'))
            return redirect('abonapp:abon_home', gid, uname)
        else:
            messages.error(request, _('fix form errors'))
    else:
        frm = forms.AdditionalTelephoneForm()
    return render(request, 'abonapp/modal_add_phone.html', {
        'form': frm,
        'gid': gid,
        'uname': uname
    })


@login_required
@only_admins
@permission_required('abonapp.delete_additionaltelephone')
def tel_del(request, gid: int, uname):
    try:
        tid = lib.safe_int(request.GET.get('tid'))
        tel = models.AdditionalTelephone.objects.get(pk=tid)
        tel.delete()
        messages.success(request,
                         _('Additional telephone successfully deleted'))
    except models.AdditionalTelephone.DoesNotExist:
        messages.error(request, _('Telephone not found'))
    return redirect('abonapp:abon_home', gid, uname)


@login_required
@only_admins
@permission_required('groupapp.view_group', (Group, 'pk', 'gid'))
def phonebook(request, gid):
    res_format = request.GET.get('f')
    t1 = models.Abon.objects.filter(
        group__id=int(gid)
    ).only('telephone', 'fio').values_list(
        'telephone', 'fio'
    )
    t2 = models.AdditionalTelephone.objects.filter(
        abon__group__id=gid
    ).only(
        'telephone', 'owner_name'
    ).values_list(
        'telephone', 'owner_name'
    )
    telephones = tuple(t1) + tuple(t2)
    if res_format == 'csv':
        import csv
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="phones.csv"'
        writer = csv.writer(response, quoting=csv.QUOTE_NONNUMERIC)
        for row in telephones:
            writer.writerow(row)
        return response
    return render(request, 'abonapp/modal_phonebook.html', {
        'tels': telephones,
        'gid': gid
    })


@login_required
@only_admins
@permission_required('groupapp.view_group', (Group, 'pk', 'gid'))
def abon_export(request, gid):
    res_format = request.GET.get('f')

    if request.method == 'POST':
        frm = forms.ExportUsersForm(request.POST)
        if frm.is_valid():
            cleaned_data = frm.clean()
            fields = cleaned_data.get('fields')
            subscribers = models.Abon.objects.filter(group__id=gid).only(
                *fields).values_list(*fields)
            if res_format == 'csv':
                import csv
                response = HttpResponse(content_type='text/csv')
                response[
                    'Content-Disposition'
                ] = 'attachment; filename="users.csv"'
                writer = csv.writer(response, quoting=csv.QUOTE_NONNUMERIC)
                display_values = (
                    f[1] for f in frm.fields['fields'].choices if
                    f[0] in fields
                )
                writer.writerow(display_values)
                for row in subscribers:
                    writer.writerow(row)
                return response
            else:
                messages.info(
                    request,
                    _('Unexpected format %(export_format)s') % {
                        'export_format': res_format
                    }
                )
                return redirect('abonapp:group_list')
        else:
            messages.error(request, _('fix form errors'))
            return redirect('abonapp:group_list')
    else:
        frm = forms.ExportUsersForm()
    return render(request, 'abonapp/modal_export.html', {
        'gid': gid,
        'form': frm
    })


@login_required
@only_admins
@permission_required('groupapp.view_group', (Group, 'pk', 'gid'))
def add_edit_periodic_pay(request, gid: int, uname, periodic_pay_id=0):
    if periodic_pay_id == 0:
        if not request.user.has_perm('abonapp.add_periodicpayforid'):
            raise PermissionDenied
        periodic_pay_instance = models.PeriodicPayForId()
    else:
        if not request.user.has_perm('abonapp.change_periodicpayforid'):
            raise PermissionDenied
        periodic_pay_instance = get_object_or_404(
            models.PeriodicPayForId,
            pk=periodic_pay_id
        )
    if request.method == 'POST':
        frm = forms.PeriodicPayForIdForm(
            request.POST,
            instance=periodic_pay_instance
        )
        if frm.is_valid():
            abon = get_object_or_404(models.Abon, username=uname)
            inst = frm.save(commit=False)
            inst.account = abon
            inst.save()
            messages.success(request, _('Periodic pays has been designated'))
        else:
            messages.error(request, _('Something wrong in form'))
        return redirect('abonapp:abon_services', gid, uname)
    else:
        frm = forms.PeriodicPayForIdForm(instance=periodic_pay_instance)
    return render(request, 'abonapp/modal_periodic_pay.html', {
        'form': frm,
        'gid': gid,
        'uname': uname
    })


@login_required
@only_admins
@permission_required('groupapp.view_group', (Group, 'pk', 'gid'))
@permission_required('abonapp.delete_periodicpayforid')
def del_periodic_pay(request, gid: int, uname, periodic_pay_id):
    periodic_pay_instance = get_object_or_404(
        models.PeriodicPayForId,
        pk=periodic_pay_id
    )
    if periodic_pay_instance.account.username != uname:
        uname = periodic_pay_instance.account.username
    periodic_pay_instance.delete()
    messages.success(request, _('Periodic pay successfully deleted'))
    return redirect('abonapp:abon_services', gid, uname)


class EditSibscriberMarkers(LoginAdminPermissionMixin, UpdateView):
    permission_required = 'abonapp.change_abon'
    http_method_names = ('get', 'post')
    template_name = 'abonapp/modal_user_markers.html'
    form_class = forms.MarkersForm
    model = models.Abon
    slug_url_kwarg = 'uname'
    slug_field = 'username'

    def dispatch(self, request, *args, **kwargs):
        try:
            return super(EditSibscriberMarkers, self).dispatch(
                request, *args, **kwargs
            )
        except ValidationError as e:
            messages.error(request, e)
            return self.render_to_response(self.get_context_data())

    def get_context_data(self, **kwargs):
        context = super(EditSibscriberMarkers, self).get_context_data(**kwargs)
        context['gid'] = self.kwargs.get('gid')
        context['uname'] = self.kwargs.get('uname')
        return context

    def form_invalid(self, form):
        messages.error(self.request, _('fix form errors'))
        return super(EditSibscriberMarkers, self).form_invalid(form)

    def form_valid(self, form):
        v = super(EditSibscriberMarkers, self).form_valid(form)
        messages.success(
            self.request,
            _('User flags has changed successfully')
        )
        return v


class UserSessionFree(LoginRequiredMixin, OnlyAdminsMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'abonapp.change_abon'
    model = models.Abon
    slug_url_kwarg = 'uname'
    slug_field = 'username'
    fields = 'ip_address',
    template_name = 'abonapp/modal_confirm_ip_free.html'

    def get(self, request, *args, **kwargs):
        r = super().get(request, *args, **kwargs)
        abon = self.object
        if abon.nas is None:
            messages.error(self.request, _('gateway required'))
            return redirect(
                'abonapp:abon_home',
                gid=self.kwargs.get('gid'),
                uname=self.kwargs.get('uname')
            )
        return r

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        abon = self.object
        try:
            if abon.ip_address:
                abon.free_ip_addr()
                customer_nas_command.delay(abon.pk, 'remove')
                messages.success(request, _('Ip lease has been freed'))
            else:
                messages.error(request, _('User not have ip'))
        except OperationalError as e:
            messages.error(request, e)
        return redirect(
            'abonapp:abon_home',
            gid=self.kwargs.get('gid'),
            uname=self.kwargs.get('uname')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'gid': self.kwargs.get('gid'),
        })
        return context


@login_required
@only_admins
@permission_required('abonapp.change_abon')
def attach_nas(request, gid):
    if request.method == 'POST':
        gateway_id = lib.safe_int(request.POST.get('gateway'))
        if gateway_id:
            nas = get_object_or_404(NASModel, pk=gateway_id)
            customers = models.Abon.objects.filter(group__id=gid)
            if customers.exists():
                customers.update(nas=nas)
                messages.success(
                    request,
                    _('Network access server for users in this '
                      'group, has been updated')
                )
                return redirect('abonapp:group_list')
            else:
                messages.warning(request, _('Users not found'))
        else:
            messages.error(request, _('You must select gateway'))
    return render(request, 'abonapp/modal_attach_nas.html', {
        'gid': gid,
        'nas_list': NASModel.objects.all().iterator()
    })


# API's
@login_required
@only_admins
@json_view
def abons(request):
    ablist = ({
                  'id': abn.pk,
                  'tarif_id': abn.active_tariff().tariff.pk
                  if abn.active_tariff() is not None else 0,
                  'ip': abn.ip_address
              } for abn in models.Abon.objects.iterator())

    tarlist = ({
                   'id': trf.pk,
                   'speedIn': trf.speedIn,
                   'speedOut': trf.speedOut
               } for trf in Tariff.objects.all())

    data = {
        'subscribers': ablist,
        'tariffs': tarlist
    }
    del ablist, tarlist
    return data


@login_required
@only_admins
@json_view
def search_abon(request):
    word = request.GET.get('s')
    if not word:
        return None
    results = models.Abon.objects.filter(fio__icontains=word)[:8]
    return list(
        {'id': usr.pk, 'text': "%s: %s" % (usr.username, usr.fio)}
        for usr in results
    )


class DhcpLever(SecureApiView):
    #
    # Api view for dhcp event
    #
    http_method_names = ('get',)

    @method_decorator(json_view)
    def get(self, request, *args, **kwargs):
        data = request.GET.copy()
        try:
            r = self.on_dhcp_event(data)
            if r is not None:
                return {'text': r}
            return {'status': 'ok'}
        except IntegrityError as e:
            return {'status': str(e).replace('\n', ' ')}

    @staticmethod
    def on_dhcp_event(data: Dict) -> Optional[str]:
        """
        :param data = {
            'client_ip': ip_address('127.0.0.1'),
            'client_mac': 'aa:bb:cc:dd:ee:ff',
            'switch_mac': 'aa:bb:cc:dd:ee:ff',
            'switch_port': 3,
            'cmd': 'commit'
        }"""
        try:
            action = data.get('cmd')
            if action is None:
                return '"cmd" parameter is missing'
            client_ip = data.get('client_ip')
            if client_ip is None:
                return '"client_ip" parameter is missing'
            if action == 'commit':
                return dhcp_commit(
                    client_ip, data.get('client_mac'),
                    data.get('switch_mac'), data.get('switch_port')
                )
            elif action == 'expiry':
                return dhcp_expiry(client_ip)
            elif action == 'release':
                return dhcp_release(client_ip)
            else:
                return '"cmd" parameter is invalid: %s' % action
        except lib.LogicError as e:
            print('LogicError', e)
            return str(e)
        except lib.DuplicateEntry as e:
            print('Duplicate:', e)
            return str(e)


class PayHistoryListView(LoginAdminPermissionMixin, OrderedFilteredList):
    permission_required = 'groupapp.view_group'
    context_object_name = 'pay_history'
    template_name = 'abonapp/payHistory.html'

    def get_permission_object(self):
        if hasattr(self, 'abon'):
            return self.abon.group
        return Group.objects.filter(pk=self.kwargs.get('gid')).first()

    def get_queryset(self):
        abon = get_object_or_404(models.Abon,
                                 username=self.kwargs.get('uname'))
        self.abon = abon
        pay_history = models.AbonLog.objects.filter(abon=abon).order_by('-date')
        return pay_history

    def get_context_data(self, **kwargs):
        context = {
            'group': self.abon.group,
            'abon': self.abon
        }
        context.update(kwargs)
        return super(PayHistoryListView, self).get_context_data(**context)
