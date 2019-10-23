from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import UpdateView, CreateView, DeleteView
from djing.lib.decorators import only_admins

from guardian.decorators import permission_required_or_403 as permission_required
from djing.global_base_views import OrderedFilteredList
from ip_pool import models, forms
from groupapp.models import Group


login_decs = login_required, only_admins


@method_decorator(login_decs, name='dispatch')
@method_decorator(permission_required('ip_pool.view_networkmodel'), name='dispatch')
class NetworksListView(OrderedFilteredList):
    device_kind_code = None
    template_name = 'ip_pool/network_list.html'
    context_object_name = 'networks_list'
    model = models.NetworkModel

    def get_queryset(self):
        qs = super().get_queryset()
        if isinstance(self.device_kind_code, int):
            return qs.filter(kind=self.device_kind_code)
        return qs


@method_decorator(login_decs, name='dispatch')
@method_decorator(permission_required('ip_pool.change_networkmodel'), name='dispatch')
class NetworkUpdateView(UpdateView):
    model = models.NetworkModel
    template_name = 'ip_pool/net_edit.html'
    form_class = forms.NetworkForm
    pk_url_kwarg = 'net_id'

    def form_valid(self, form):
        r = super().form_valid(form)
        messages.success(self.request, _('Network successfully updated'))
        return r


@method_decorator(login_decs, name='dispatch')
@method_decorator(permission_required('ip_pool.delete_networkmodel'), name='dispatch')
class NetworkDeleteView(DeleteView):
    model = models.NetworkModel
    pk_url_kwarg = 'net_id'
    success_url = reverse_lazy('ip_pool:networks')

    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Network has been deleted'))
        return super(NetworkDeleteView, self).delete(request, *args, **kwargs)


@method_decorator(login_decs, name='dispatch')
@method_decorator(permission_required('ip_pool.add_networkmodel'), name='dispatch')
class NetworkCreateView(CreateView):
    model = models.NetworkModel
    template_name = 'ip_pool/net_add.html'
    form_class = forms.NetworkForm

    def form_valid(self, form):
        r = super().form_valid(form)
        messages.success(self.request, _('Network has been created'))
        return r


@login_required
@method_decorator(permission_required('ip_pool.view_networkmodel'), name='dispatch')
def network_in_groups(request, net_id):
    network = get_object_or_404(models.NetworkModel, pk=net_id)
    if request.method == 'POST':
        gr = request.POST.getlist('gr')
        network.groups.clear()
        network.groups.add(*gr)
        messages.success(request, _('Successfully saved'))
        return redirect('ip_pool:net_groups', net_id)

    selected_grps = tuple(pk[0] for pk in network.groups.only('pk').values_list('pk'))
    return render(request, 'ip_pool/network_groups_available.html', {
        'object': network,
        'selected_grps': selected_grps,
        'groups': Group.objects.all().iterator()
    })
