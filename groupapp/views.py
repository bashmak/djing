from django.db.models import Count
from django.http import HttpResponseRedirect
from django.views.generic import UpdateView, CreateView, DeleteView
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext_lazy as _
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from django.contrib import messages
from django.conf import settings
from djing.lib.decorators import only_admins
from guardian.decorators import permission_required_or_403 as permission_required
from guardian.shortcuts import get_objects_for_user

from djing.global_base_views import OrderedFilteredList
from . import models
from . import forms


login_decs = login_required, only_admins


@method_decorator(login_decs, name='dispatch')
@method_decorator(permission_required('groupapp.view_group'), name='dispatch')
class GroupListView(OrderedFilteredList):
    http_method_names = ('get',)
    paginate_by = getattr(settings, 'PAGINATION_ITEMS_PER_PAGE', 10)
    template_name = 'groupapp/group_list.html'
    model = models.Group
    context_object_name = 'groups'

    def get_queryset(self):
        queryset = get_objects_for_user(self.request.user,
                                        'groupapp.view_group', klass=self.model,
                                        accept_global_perms=False)
        return queryset


@method_decorator(login_decs, name='dispatch')
@method_decorator(permission_required('groupapp.change_group'), name='dispatch')
class EditGroupView(UpdateView):
    http_method_names = ('get', 'post')
    template_name = 'groupapp/edit_group.html'
    form_class = forms.GroupForm
    model = models.Group
    pk_url_kwarg = 'group_id'
    success_url = reverse_lazy('groupapp:group_list')

    def form_valid(self, form):
        messages.success(self.request, _('Group changes has been saved'))
        return super(EditGroupView, self).form_valid(form)

    def form_invalid(self, form):
        messages.success(self.request, _('Please fix form errors'))
        return super(EditGroupView, self).form_invalid(form)


@method_decorator(login_decs, name='dispatch')
@method_decorator(permission_required('groupapp.add_group'), name='dispatch')
class AddGroupView(CreateView):
    http_method_names = ('get', 'post')
    template_name = 'groupapp/add_group.html'
    form_class = forms.GroupForm
    success_url = reverse_lazy('groupapp:group_list')

    def form_valid(self, form):
        messages.success(self.request, _('New group are created'))
        return super(AddGroupView, self).form_valid(form)

    def form_invalid(self, form):
        messages.success(self.request, _('Please fix form errors'))
        return super(AddGroupView, self).form_invalid(form)


@method_decorator(login_decs, name='dispatch')
@method_decorator(permission_required('groupapp:delete_group'), name='dispatch')
class DeleteGroupView(DeleteView):
    model = models.Group
    pk_url_kwarg = 'group_id'
    success_url = reverse_lazy('groupapp:group_list')

    def delete(self, request, *args, **kwargs):
        group_id = self.kwargs.get('group_id')
        group_with_subscribers = models.Group.objects.annotate(
            subscribers_count=Count('abon')
        ).filter(subscribers_count__gt=0, pk=group_id).first()
        if group_with_subscribers is not None:
            messages.error(request, _('Group is contain subscribers. Remove them before delete group'))
            return HttpResponseRedirect(self.success_url)
        return super().delete(request, *args, **kwargs)
