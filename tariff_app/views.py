from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Count
from django.urls import reverse_lazy
from django.utils.translation import ugettext as _
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.views.generic import DeleteView
from guardian.decorators import permission_required_or_403 as permission_required

from djing.global_base_views import OrderedFilteredList
from djing.lib.mixins import LoginAdminMixin
from abonapp.models import Abon
from .models import Tariff, PeriodicPay
from djing import lib
from djing.lib.decorators import only_admins
from . import forms


login_decs = login_required, only_admins


class TariffsListView(LoginAdminMixin, PermissionRequiredMixin, OrderedFilteredList):
    """
    Show Services(Tariffs) list
    """
    permission_required = 'tariff_app.view_tariff'
    template_name = 'tariff_app/tarifs.html'
    context_object_name = 'tariflist'
    model = Tariff
    queryset = Tariff.objects.annotate(usercount=Count('linkto_tariff__abon'))


@login_required
@only_admins
@permission_required('tariff_app.change_tariff')
def edit_tarif(request, tarif_id=0):
    tarif_id = lib.safe_int(tarif_id)

    if tarif_id == 0:
        if not request.user.has_perm('tariff_app.add_tariff'):
            raise PermissionDenied
        tarif = None
    else:
        if not request.user.has_perm('tariff_app.change_tariff'):
            raise PermissionDenied
        tarif = get_object_or_404(Tariff, pk=tarif_id)

    if request.method == 'POST':
        frm = forms.TariffForm(request.POST, instance=tarif)
        if frm.is_valid():
            service = frm.save()
            if tarif is None:
                request.user.log(request.META, 'csrv', '"%(title)s", "%(descr)s", %(amount).2f' % {
                    'title': service.title or '-',
                    'descr': service.descr or '-',
                    'amount': service.amount or 0.0
                })
            messages.success(request, _('Service has been saved'))
            return redirect('tarifs:edit', tarif_id=service.pk)
        else:
            messages.warning(request, _('Some fields were filled incorrect, please try again'))
    else:
        frm = forms.TariffForm(instance=tarif)

    return render(request, 'tariff_app/editTarif.html', {
        'form': frm,
        'tarif_id': tarif_id
    })


class TariffDeleteView(LoginAdminMixin, PermissionRequiredMixin, DeleteView):
    permission_required = 'tariff_app.delete_tariff'
    model = Tariff
    pk_url_kwarg = 'tid'
    success_url = reverse_lazy('tarifs:home')

    def delete(self, request, *args, **kwargs):
        res = super().delete(request, *args, **kwargs)
        request.user.log(request.META, 8, '"%(title)s", "%(descr)s", %(amount).2f' % {
            'title': self.object.title or '-',
            'descr': self.object.descr or '-',
            'amount': self.object.amount or 0.0
        })
        messages.success(request, _('Service has been deleted'))
        return res

    def get_context_data(self, **kwargs):
        kwargs['tid'] = self.kwargs.get('tid')
        return super().get_context_data(**kwargs)


class PeriodicPaysListView(LoginAdminMixin, PermissionRequiredMixin, OrderedFilteredList):
    permission_required = 'tariff_app.view_periodicpay'
    context_object_name = 'pays'
    model = PeriodicPay
    template_name = 'tariff_app/periodic_pays/list.html'


@login_required
@only_admins
def periodic_pay(request, pay_id=0):
    if pay_id != 0:
        pay_inst = get_object_or_404(PeriodicPay, pk=pay_id)
        if not request.user.has_perm('tariff_app.change_periodicpay'):
            raise PermissionDenied
    else:
        pay_inst = None
        if not request.user.has_perm('tariff_app.add_periodicpay'):
            raise PermissionDenied
    if request.method == 'POST':
        frm = forms.PeriodicPayForm(request.POST, instance=pay_inst)
        if frm.is_valid():
            new_periodic_pay = frm.save()
            if pay_inst is None:
                comment = _('New periodic pay successfully created')
            else:
                comment = _('Periodic pay has been changed')
            messages.success(request, comment)
            return redirect('tarifs:periodic_pay_edit', new_periodic_pay.pk)
        else:
            messages.error(request, _('Some fields were filled incorrect, please try again'))
    else:
        frm = forms.PeriodicPayForm(instance=pay_inst)

    return render(request, 'tariff_app/periodic_pays/add_edit.html', {
        'pay_instance': pay_inst,
        'form': frm
    })


class ServiceUsers(LoginAdminMixin, OrderedFilteredList):
    template_name = 'tariff_app/service_users.html'
    model = Abon

    def get_queryset(self):
        tarif_id = self.kwargs.get('tarif_id')
        return Abon.objects.filter(current_tariff__tariff__id=tarif_id).select_related('group')

    def get_context_data(self, **kwargs):
        if hasattr(self, 'tariff'):
            tariff = getattr(self, 'tariff')
        else:
            tarif_id = self.kwargs.get('tarif_id')
            tariff = get_object_or_404(Tariff, pk=tarif_id)
            setattr(self, 'tariff', tariff)
        self.tariff = tariff
        context = {
            'tariff': tariff,
            'total': self.object_list.count()
        }
        context.update(kwargs)
        return super().get_context_data(**context)
