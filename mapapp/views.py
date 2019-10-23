from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404, resolve_url
from django.utils.translation import gettext_lazy as _, gettext
from django.utils.decorators import method_decorator
from django.db.models import Count
from django.views.generic import ListView
from django.conf import settings

from groupapp.models import Group
from .models import Dot
from .forms import DotForm
from djing.lib import safe_int
from djing.lib.decorators import only_admins, json_view
from devapp.models import Device
from guardian.decorators import permission_required


login_decs = login_required, only_admins


class BaseListView(ListView):
    http_method_names = ('get',)
    paginate_by = getattr(settings, 'PAGINATION_ITEMS_PER_PAGE', 10)


@login_required
@only_admins
def home(request):
    if not request.user.is_superuser:
        return redirect('/')
    dots = Dot.objects.all()
    groups = Group.objects.all()
    return render(request, 'maps/ya_index.html', {
        'dots': dots.iterator(),
        'groups': groups.iterator()
    })


@method_decorator(login_decs, name='dispatch')
class OptionsListView(BaseListView):
    template_name = 'maps/options.html'
    model = Dot
    context_object_name = 'dots'

    def get(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            return redirect('/')
        return super(OptionsListView, self).get(request, *args, **kwargs)


@login_required
@only_admins
def dot_edit(request, did=0):
    if not request.user.is_superuser:
        return redirect('/')
    try:
        if did == 0:
            dot = Dot()
            if not request.user.has_perm('mapapp.add_dot'):
                raise PermissionDenied
        else:
            if not request.user.has_perm('mapapp.change_dot'):
                raise PermissionDenied
            dot = Dot.objects.get(id=did)

        if request.method == 'POST':
            frm = DotForm(request.POST, request.FILES, instance=dot)
            if frm.is_valid():
                new_dot = frm.save()
                messages.success(request, _('Map point has been saved'))
                return redirect('mapapp:edit_dot', new_dot.pk)
            else:
                messages.error(request, _('fix form errors'))
        else:
            frm = DotForm(instance=dot)

        return render(request, 'maps/dot.html', {
            'dot': dot,
            'form': frm
        })

    except Dot.DoesNotExist:
        messages.error(request, _('Map point does not exist'))
        return redirect('mapapp:options')


@login_required
@only_admins
@permission_required('mapapp.delete_dot')
def remove(request, did):
    try:
        dot = Dot.objects.get(id=did)
        title = dot.title
        dot.delete()
        messages.success(request, _("Map point '%(title)s' has been deleted") % {'title': title})
    except Dot.DoesNotExist:
        messages.error(request, _('Map point does not exist'))
    return redirect('mapapp:options')


@login_required
@only_admins
@json_view
def get_dots(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('you have not super user')
    dots = Dot.objects.prefetch_related('devices').annotate(devcount=Count('devices')).defer('attachment').iterator()

    def fill_dev(dev: Device):
        return {
            'status': dev.status,
            'comment': dev.comment
        } if dev is not None else None

    is_obtain_pk = request.GET.get('is_obtain_pk')

    if is_obtain_pk == 'on':
        res = dict()
        for e in dots:
            res[str(e.pk)] = {
                'devcount': e.devcount,
                'latitude': e.latitude,
                'longitude': e.longitude,
                'title': e.title,
                'pk': e.pk,
                'device': fill_dev(e.devices.first())
            }
    else:
        res = [{
            'devcount': e.devcount,
            'latitude': e.latitude,
            'longitude': e.longitude,
            'title': e.title,
            'pk': e.pk,
            'device': fill_dev(e.devices.first())
        } for e in dots]

    return res


@login_required
@only_admins
def modal_add_dot(request):
    if not request.user.has_perm('mapapp.add_dot'):
        return render(request, '403_for_modal.html')
    if request.method == 'POST':
        frm = DotForm(request.POST, request.FILES)
        if frm.is_valid():
            new_dot = frm.save()
            res = {
                'latitude': new_dot.latitude,
                'longitude': new_dot.longitude,
                'title': new_dot.title,
                'pk': new_dot.pk
            }
        else:
            res = {
                'error': _('fix form errors')
            }
        from json import dumps
        return HttpResponse(dumps(res))
    else:
        coords = request.GET.get('coords')
        lat, lon = coords.split(',')
        frm = DotForm(initial={'latitude': lat, 'longitude': lon})
    return render(request, 'maps/modal_add_dot.html', {
        'coords': coords,
        'form': frm
    })


@login_required
@only_admins
def preload_devices(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden('you have not super user')
    grp_id = request.GET.get('grp')
    dot_id = request.GET.get('dot')
    all_devices = Device.objects.filter(group__id=grp_id)
    dot_devices = Device.objects.filter(dot__id=dot_id)
    dot_devices_ids = tuple(dev.pk for dev in dot_devices.iterator())
    del dot_devices

    return render(request, 'maps/preload_devices_tmpl.html', {
        'all_devices': all_devices.iterator(),
        'dot_devices_ids': dot_devices_ids
    }, content_type='text/html')


@login_required
@only_admins
def dot_tooltip(request):
    if not request.user.is_superuser:
        return render(request, '403_for_modal.html')
    d = request.GET.get('d')
    devs, dot = None, None
    try:
        dot = Dot.objects.get(id=d)
        devs = dot.devices.all()
    except Dot.DoesNotExist:
        pass
    return render(request, 'maps/map_tooltip.html', {
        'devs': devs.iterator(),
        'dot': dot
    })


@login_required
@only_admins
def add_dev(request, did):
    if not request.user.is_superuser:
        return redirect('/')
    groups = Group.objects.all()
    dot = get_object_or_404(Dot, pk=did)
    param_user_group = safe_int(request.GET.get('grp'))

    if request.method == 'POST':
        selected_devs = request.POST.getlist('dv')
        selected_user_group = safe_int(request.POST.get('selected_user_group'))

        existing_devs = Device.objects.filter(group__id=selected_user_group or param_user_group)
        if existing_devs.exists():
            dot.devices.remove(*(dev.pk for dev in existing_devs.iterator()))
        dot.devices.add(*selected_devs)

        url = resolve_url('mapapp:add_dev', did=dot.pk)
        return HttpResponseRedirect("%s?grp=%d" % (url, selected_user_group or param_user_group))
    else:
        existing_devs = Device.objects.filter(group=param_user_group)
    return render(request, 'maps/add_device.html', {
        'groups': groups.iterator(),
        'dot': dot,
        'existing_devs': existing_devs.iterator(),
        'grp': param_user_group,
        'dot_devices_ids': [dev.pk for dev in Device.objects.filter(dot=dot)]
    })


@login_required
@only_admins
@json_view
def resolve_dots_by_group(request, grp_id):
    if not request.user.is_superuser:
        return HttpResponseForbidden('you have not super user')
    devs = Device.objects.filter(group__id=grp_id)
    dots = Dot.objects.filter(devices__in=devs).only('pk').values_list('pk')
    res = [dot[0] for dot in dots]
    return res


@login_required
@only_admins
def to_single_dev(request):
    dot_id = safe_int(request.GET.get('dot_id'))
    if dot_id <= 0:
        return HttpResponseBadRequest
    dev = Device.objects.filter(dot__id=dot_id).first()
    if dev is None:
        messages.error(request, gettext('Devices is not found on the dot'))
        return redirect('mapapp:edit_dot', dot_id)
    grp_id = dev.group.pk
    return redirect('devapp:view', grp_id, dev.pk)
