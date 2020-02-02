import re
from ipaddress import ip_address

from kombu.exceptions import OperationalError

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.db.models import Q, Count
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404, resolve_url
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _, gettext
from django.views.generic import DetailView, DeleteView, UpdateView, CreateView
from djing import global_base_views, IP_ADDR_REGEX, ping, get_object_or_None
from djing.lib import safe_int, ProcessLocked, DuplicateEntry
from djing.lib.decorators import json_view
from djing.lib.decorators import only_admins, hash_auth_view
from djing.lib.mixins import LoginAdminPermissionMixin, LoginAdminMixin
# from djing.tasks import multicast_email_notify
from easysnmp import EasySNMPTimeoutError, EasySNMPError
from groupapp.models import Group
from abonapp.models import Abon
from profiles.models import UserProfile
from messenger.tasks import multicast_viber_notify
from guardian.decorators import permission_required_or_403 as permission_required
from guardian.shortcuts import get_objects_for_user
from devapp.forms import DeviceForm, PortForm, DeviceExtraDataForm, DeviceRebootForm
from devapp.models import Device, Port, DeviceDBException, DeviceMonitoringException
from devapp.tasks import onu_register
from devapp.base_intr import DeviceImplementationError, DeviceConfigurationError
from devapp import expect_scripts


class DevicesListView(LoginAdminPermissionMixin,
                      global_base_views.OrderedFilteredList):
    context_object_name = 'devices'
    template_name = 'devapp/devices.html'
    permission_required = 'devapp.view_device'

    def get_queryset(self):
        group_id = safe_int(self.kwargs.get('group_id'))
        queryset = Device.objects.filter(group__pk=group_id) \
            .select_related('group') \
            .only('comment', 'mac_addr', 'devtype', 'group', 'pk',
                  'ip_address')
        return queryset

    def get_context_data(self, **kwargs):
        group_id = safe_int(self.kwargs.get('group_id'))
        context = super(DevicesListView, self).get_context_data(**kwargs)
        context['group'] = get_object_or_404(Group, pk=group_id)
        return context

    def dispatch(self, request, *args, **kwargs):
        try:
            response = super(DevicesListView, self).dispatch(request, *args,
                                                             **kwargs)
        except (DeviceDBException, DeviceMonitoringException) as e:
            messages.error(request, e)
            response = HttpResponse('Error')
        return response


class DevicesWithoutGroupsListView(LoginAdminPermissionMixin,
                                   global_base_views.OrderedFilteredList):
    context_object_name = 'devices'
    template_name = 'devapp/devices_null_group.html'
    queryset = Device.objects.filter(group=None).only('comment', 'devtype',
                                                      'pk', 'ip_address')
    permission_required = 'devapp.view_device'


class DeviceDeleteView(LoginAdminPermissionMixin, DeleteView):
    model = Device
    pk_url_kwarg = 'device_id'
    permission_required = 'devapp.delete_device'

    def get_success_url(self):
        return resolve_url('devapp:devs',
                           group_id=self.object.group.pk
                           if self.object.group else 0)

    def delete(self, request, *args, **kwargs):
        res = super().delete(request, *args, **kwargs)
        try:
            request.user.log(request.META, 'ddev', 'ip %s, mac: %s, "%s"' % (
                self.object.ip_address or '-',
                self.object.mac_addr or '-',
                self.object.comment or '-'
            ))
            onu_register.delay(
                tuple(dev.pk for dev in Device.objects.exclude(group=None).only('pk').iterator())
            )
        except (DeviceDBException, PermissionError, OperationalError) as e:
            messages.error(request, e)
        messages.success(request, _('Device successfully deleted'))
        return res


class DeviceUpdate(LoginAdminPermissionMixin, UpdateView):
    template_name = 'devapp/dev.html'
    context_object_name = 'dev'
    model = Device
    form_class = DeviceForm
    pk_url_kwarg = 'device_id'
    device_group = None
    already_dev = None
    permission_required = 'devapp.view_device'

    def post(self, request, *args, **kwargs):
        if not request.user.has_perm('devapp.change_device'):
            raise PermissionDenied
        try:
            return super().post(request, *args, **kwargs)
        except IntegrityError as e:
            if 'unique constraint' in str(e):
                messages.error(request, _('Duplicate user and port: %s') % e)
            else:
                messages.error(request, e)
        return self.form_invalid(self.get_form())

    def form_valid(self, form):
        # check if that device is exist
        device_id = self.kwargs.get(self.pk_url_kwarg)
        try:
            already_dev = self.model.objects.exclude(pk=device_id).get(
                mac_addr=self.request.POST.get('mac_addr'))
            self.already_dev = already_dev
            if already_dev.group:
                messages.warning(
                    self.request,
                    _('You have redirected to existing device')
                )
                return redirect(
                    'devapp:view', already_dev.group.pk,
                    already_dev.pk
                )
            else:
                messages.warning(
                    self.request,
                    _('Please attach group for device')
                )
                return redirect('devapp:fix_device_group', already_dev.pk)
        except Device.DoesNotExist:
            pass
        r = super().form_valid(form)
        # change device info in dhcpd.conf
        try:
            onu_register.delay(
                tuple(dev.pk for dev in Device.objects.exclude(group=None).only('pk').iterator())
            )
            messages.success(self.request, _('Device info has been saved'))
        except (PermissionError, OperationalError) as e:
            messages.error(self.request, e)
        return r

    def dispatch(self, request, *args, **kwargs):
        group_id = self.kwargs.get('group_id')
        device_group = get_object_or_404(Group, pk=group_id)
        if not request.user.has_perm('groupapp.view_group', device_group):
            raise PermissionDenied
        self.device_group = device_group
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        messages.error(
            self.request,
            _('Form is invalid, check fields and try again')
        )
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_parent_dev'] = self.object.parent_dev
        context['group'] = self.device_group
        context['already_dev'] = self.already_dev
        return context


class DeviceCreateView(LoginAdminMixin, PermissionRequiredMixin, CreateView):
    template_name = 'devapp/add_dev.html'
    context_object_name = 'dev'
    model = Device
    form_class = DeviceForm
    permission_required = 'devapp.add_device'
    device_group = None
    already_dev = None

    def form_valid(self, form):
        # check if that device is exist
        try:
            already_dev = self.model.objects.get(
                mac_addr=self.request.POST.get('mac_addr')
            )
            self.already_dev = already_dev
            if already_dev.group:
                messages.warning(
                    self.request,
                    _('You have redirected to existing device')
                )
                return redirect(
                    'devapp:view', already_dev.group.pk,
                    already_dev.pk
                )
            else:
                messages.warning(
                    self.request,
                    _('Please attach group for device')
                )
                return redirect('devapp:fix_device_group', already_dev.pk)
        except Device.DoesNotExist:
            pass
        r = super().form_valid(form)
        # change device info in dhcpd.conf
        try:
            self.request.user.log(
                self.request.META, 2,
                'ip %s, mac: %s, "%s"' % (
                    self.object.ip_address,
                    self.object.mac_addr,
                    self.object.comment
                ))
            onu_register.delay(
                tuple(dev.pk for dev in Device.objects.exclude(group=None).only('pk').iterator())
            )
            messages.success(self.request, _('Device info has been saved'))
        except (PermissionError, OperationalError) as e:
            messages.error(self.request, e)
        return r

    def dispatch(self, request, *args, **kwargs):
        group_id = self.kwargs.get('group_id')
        device_group = get_object_or_404(Group, pk=group_id)
        if not request.user.has_perm('groupapp.view_group', device_group):
            raise PermissionDenied
        self.device_group = device_group
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        if self.request.method == 'GET':
            return {
                'group': self.device_group,
                'devtype': self.request.GET.get('t'),
                'mac_addr': self.request.GET.get('mac'),
                'comment': self.request.GET.get('c'),
                'ip_address': self.request.GET.get('ip'),
                'man_passw': getattr(settings, 'DEFAULT_SNMP_PASSWORD', ''),
                'snmp_extra': self.request.GET.get('n') or ''
            }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['group'] = self.device_group
        context['already_dev'] = self.already_dev
        parent_device_id = self.request.GET.get('pdev')
        context['selected_parent_dev'] = get_object_or_None(
            Device, pk=parent_device_id)
        return context


class DeviceUpdateExtra(LoginAdminPermissionMixin, UpdateView):
    template_name = 'devapp/modal_device_extra_edit.html'
    model = Device
    form_class = DeviceExtraDataForm
    pk_url_kwarg = 'device_id'
    permission_required = 'devapp.change_device'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['group_id'] = self.kwargs.get('group_id')
        return context

    def form_valid(self, form):
        r = super().form_valid(form)
        messages.success(self.request, _('Device extra data has '
                                         'successfully updated'))
        return r


class ShowSubscriberOnPort(LoginAdminMixin,
                           global_base_views.RedirectWhenErrorMixin,
                           DetailView):
    template_name = 'devapp/manage_ports/modal_show_subscriber_on_port.html'
    http_method_names = ('get',)

    def get_object(self, queryset=None):
        dev_id = self.kwargs.get('device_id')
        port_id = self.kwargs.get('port_id')
        try:
            obj = Abon.objects.get(device_id=dev_id, dev_port_id=port_id)
        except Abon.DoesNotExist:
            raise Http404(gettext('Subscribers on port does not exist'))
        except Abon.MultipleObjectsReturned:
            errmsg = gettext('More than one subscriber on device port')
            # messages.error(self.request, errmsg)
            raise global_base_views.RedirectWhenError(
                resolve_url('devapp:fix_port_conflict',
                            group_id=self.kwargs.get('group_id'),
                            device_id=dev_id,
                            port_id=port_id),
                errmsg
            )
        return obj


@login_required
@only_admins
@permission_required('devapp.add_port')
def add_ports(request, group_id: int, device_id: int):
    class TempPort:
        __slots__ = 'pid', 'text', 'placeholder', 'status', 'from_db', 'pk'

        def __init__(self, pid, text, status, from_db, pk=None, placeholder=None):
            self.pid = pid
            self.text = text
            self.placeholder = placeholder
            self.status = status
            self.from_db = from_db
            self.pk = pk

        def __eq__(self, other):
            return self.pid == other.pid

        def __hash__(self):
            return self.pid

        def __str__(self):
            return "p:%d\tT:%s" % (self.pid, self.text)

    device = get_object_or_404(Device, pk=device_id)
    res_ports = list()
    try:
        if device.group is None:
            messages.error(request,
                           _('Device does not have a group, please fix that'))
            return redirect('devapp:fix_device_group', device.pk)
        if request.method == 'POST':
            ports = zip(
                request.POST.getlist('p_text'),
                request.POST.getlist('pids')
            )
            for port_text, port_num in ports:
                if port_text == '' or port_text is None:
                    continue
                try:
                    port = Port.objects.get(num=port_num, device=device)
                    port.descr = port_text
                    port.save(update_fields=('descr',))
                except Port.DoesNotExist:
                    Port.objects.create(
                        num=port_num,
                        device=device,
                        descr=port_text,
                        operating_mode=0
                    )

        db_ports = Port.objects.filter(device=device)
        db_ports = tuple(
            TempPort(p.num, p.descr, None, True, p.pk) for p in db_ports)

        manager = device.get_manager_object()
        ports = manager.get_ports()
        if ports is not None:
            ports = tuple(TempPort(p.num, None, p.st, False, placeholder=p.nm) for p in ports)
            res_ports = set(db_ports + ports)
        else:
            res_ports = db_ports

    except Device.DoesNotExist:
        messages.error(request, _('Device does not exist'))
        return redirect('devapp:group_list')
    except DeviceDBException as e:
        messages.error(request, e)
    except EasySNMPTimeoutError:
        messages.error(request, _('wait for a reply from the SNMP Timeout'))
    return render(request, 'devapp/manage_ports/add_ports.html', {
        'ports': res_ports,
        'dev': device
    })


@login_required
@only_admins
@permission_required('devapp.delete_port')
def delete_single_port(request, group_id, device_id, port_id):
    try:
        if request.method == 'POST':
            if request.POST.get('confirm') == 'yes':
                Port.objects.get(pk=port_id).delete()
                messages.success(request, _('Port successfully removed'))
        else:
            return render(request, 'devapp/manage_ports/modal_del_port.html', {
                'grp': group_id,
                'did': device_id,
                'port_id': port_id
            })
    except Port.DoesNotExist:
        messages.error(request, _('Port does not exist'))
    except DeviceDBException as e:
        messages.error(request, e)
    return redirect('devapp:view', group_id, device_id)


class EditSinglePort(LoginAdminPermissionMixin, UpdateView):
    pk_url_kwarg = 'port_id'
    permission_required = 'devapp.change_port'
    template_name = 'devapp/manage_ports/modal_add_edit_port.html'
    model = Port
    form_class = PortForm

    def dispatch(self, request, *args, **kwargs):
        try:
            return super(EditSinglePort, self).dispatch(request, *args, **kwargs)
        except (DeviceDBException, DuplicateEntry) as e:
            messages.error(request, e)
        group_id = self.kwargs.get('group_id')
        device_id = self.kwargs.get('device_id')
        return redirect('devapp:view', group_id, device_id)

    def form_valid(self, form):
        messages.success(self.request, _('Port successfully saved'))
        return super(EditSinglePort, self).form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _(
                    'Form is invalid, check fields and try again'))
        return super(EditSinglePort, self).form_invalid(form)

    def get_success_url(self):
        group_id = self.kwargs.get('group_id')
        device_id = self.kwargs.get('device_id')
        return resolve_url('devapp:view', group_id, device_id)

    def get_context_data(self, **kwargs):
        group_id = self.kwargs.get('group_id')
        context = super(EditSinglePort, self).get_context_data(**kwargs)
        context['did'] = self.object.device.pk
        context['gid'] = group_id
        return super(EditSinglePort, self).get_context_data(**context)


@login_required
@only_admins
@permission_required('devapp.add_port')
def add_single_port(request, group_id, device_id):
    try:
        device = Device.objects.get(pk=device_id)
        if request.method == 'POST':
            frm = PortForm(request.POST, instance=Port(device=device))
            if frm.is_valid():
                frm.save()
                messages.success(request, _('Port successfully saved'))
                return redirect('devapp:view', group_id, device_id)
            else:
                messages.error(request, _(
                    'Form is invalid, check fields and try again'))
        else:
            frm = PortForm(initial={
                'num': request.GET.get('n'),
                'descr': request.GET.get('t')
            })
        return render(request, 'devapp/manage_ports/modal_add_edit_port.html',
                      {
                          'did': device_id,
                          'gid': group_id,
                          'form': frm
                      })
    except Device.DoesNotExist:
        messages.error(request, _('Device does not exist'))
    except (DeviceDBException, DuplicateEntry) as e:
        messages.error(request, e)
    return redirect('devapp:view', group_id, device_id)


@login_required
@only_admins
@permission_required('devapp.view_device')
def devview(request, group_id: int, device_id: int):
    ports, manager = None, None
    device = get_object_or_404(Device, id=device_id)

    if not device.group:
        messages.warning(request, _('Please attach group for device'))
        return redirect('devapp:fix_device_group', device.pk)

    template_name = 'generic_switch.html'
    try:
        if device.ip_address and not ping(str(device.ip_address)):
            messages.error(request, _('Dot was not pinged'))
        if device.man_passw:
            manager = device.get_manager_object()
            ports = tuple(manager.get_ports())
            if ports is not None and len(ports) > 0 and isinstance(
                    ports[0],
                    Exception
            ):
                messages.error(request, ports[0])
                ports = ports[1]
            template_name = manager.get_template_name()
        else:
            messages.warning(request, _('Not Set snmp device password'))

        # unregistered units
        unregistered = []
        if hasattr(manager, 'get_fibers'):
            for fiber in manager.get_fibers():
                for onu in manager.get_units_unregistered(int(fiber.get('fb_id'))):
                    if onu:
                        unregistered.append(onu)
        return render(request, 'devapp/custom_dev_page/' + template_name, {
            'dev': device,
            'ports': ports,
            'dev_accs': Abon.objects.filter(device=device),
            'dev_manager': manager,
            'unregistered': unregistered,
            'ports_db': Port.objects.filter(device=device).annotate(
                num_abons=Count('abon')
            ),
        })
    except EasySNMPError as e:
        messages.error(request,
                       "%s: %s" % (gettext('SNMP error on device'), e))
    except (DeviceDBException, DeviceImplementationError) as e:
        messages.error(request, e)
    return render(request, 'devapp/custom_dev_page/' + template_name, {
        'dev': device
    })


class RebootDevice(LoginAdminPermissionMixin, UpdateView):
    permission_required = 'devapp.change_device'
    template_name = 'devapp/modal_device_reboot.html'
    model = Device
    pk_url_kwarg = 'device_id'
    form_class = DeviceRebootForm

    def form_valid(self, form):
        device = self.object
        manager = device.get_manager_object()
        is_save = form.cleaned_data.get('is_save')
        try:
            r = manager.reboot(save_before_reboot=is_save)
            if isinstance(r, tuple) and len(r) == 2:
                ret, ret_text = r
                if ret == 0:
                    messages.success(self.request, ret_text or _('Signal for reboot has been sent'))
                elif ret is None:
                    messages.warning(self.request, ret_text or _('Command return nothing'))
                else:
                    messages.error(self.request, ret_text or _('Command returned %s') % str(ret))
            elif r is None:
                messages.warning(self.request, _('Command return nothing'))
            else:
                messages.warning(self.request, _('Command return unknown'))
        except DeviceConfigurationError as e:
            messages.error(self.request, e)
        return redirect(
            'devapp:view',
            device.group.pk if device.group is not None else 0,
            device.pk
        )


@login_required
@only_admins
@permission_required('devapp.can_toggle_ports')
def toggle_port(request, device_id: str, port_id: str, status=0):
    status = int(status)
    port_id = int(port_id)
    device = get_object_or_404(Device, id=int(device_id))
    try:
        if ping(device.ip_address):
            if device.man_passw:
                manager = device.get_manager_object()
                ports = tuple(manager.get_ports())
                if status:
                    ports[port_id - 1].enable()
                else:
                    ports[port_id - 1].disable()
            else:
                messages.warning(request, _('Not Set snmp device password'))
        else:
            messages.error(request, _('Dot was not pinged'))
    except EasySNMPTimeoutError:
        messages.error(request, _('wait for a reply from the SNMP Timeout'))
    except EasySNMPError as e:
        messages.error(request, 'EasySNMPError: %s' % e)
    return redirect('devapp:view',
                    device.group.pk if device.group is not None else 0,
                    device_id)


class GroupsListView(LoginAdminMixin, global_base_views.OrderedFilteredList):
    context_object_name = 'groups'
    template_name = 'devapp/group_list.html'
    model = Group

    def get_queryset(self):
        groups = get_objects_for_user(self.request.user,
                                      'groupapp.view_group', klass=Group,
                                      accept_global_perms=False)
        return groups


@login_required
@only_admins
@json_view
def search_dev(request):
    word = request.GET.get('s')
    if word is None or word == '':
        results = {'id': 0, 'text': ''}
    else:
        qs = Q(comment__icontains=word)
        try:
            ip = ip_address(word)
            qs |= Q(ip_address=str(ip))
        except ValueError:
            pass
        results = Device.objects.filter(qs).only('pk', 'ip_address',
                                                 'comment')[:16]
        results = tuple({
            'id': device.pk,
            'text': "%s: %s" % (
                device.ip_address or '', device.comment
            )
        } for device in results)
    return results


@login_required
@only_admins
def fix_device_group(request, device_id):
    device = get_object_or_404(Device, pk=device_id)
    try:
        if request.method == 'POST':
            frm = DeviceForm(request.POST, instance=device)
            if frm.is_valid():
                ch_dev = frm.save()
                if ch_dev.group:
                    messages.success(request, _('Device fixed'))
                    return redirect('devapp:devs', ch_dev.group.pk)
                else:
                    messages.error(
                        request,
                        _('Please attach group for device')
                    )
            else:
                messages.error(
                    request, _('Form is invalid, check fields and try again')
                )
        else:
            frm = DeviceForm(instance=device)
    except ValueError:
        return HttpResponse('ValueError')
    return render(request, 'devapp/fix_dev_group.html', {
        'form': frm,
        'dev': device,
        'selected_parent_dev': device.parent_dev
    })


@login_required
@only_admins
@json_view
def fix_onu(request):
    mac = request.GET.get('cmd_param')
    status = 1
    text = '<span class="glyphicon glyphicon-exclamation-sign"></span>'
    try:
        onu = Device.objects.get(mac_addr=mac, devtype=3)
        parent = onu.parent_dev
        if parent is not None:
            manobj = parent.get_manager_object()
            ports = manobj.get_list_keyval('.1.3.6.1.4.1.3320.101.10.1.1.3')
            text = '<span class="glyphicon glyphicon-ok"></span> <span class="hidden-xs">%s</span>' % \
                   (_('Device with mac address %(mac)s does not exist') % {
                       'mac': mac
                   })
            for srcmac, snmpnum in ports:
                # convert bytes mac address to str presentation mac address
                real_mac = ':'.join('%x' % ord(i) for i in srcmac)
                if mac == real_mac:
                    onu.snmp_extra = str(snmpnum)
                    onu.save(update_fields=('snmp_extra',))
                    status = 0
                    text = '<span class="glyphicon glyphicon-ok"></span> <span class="hidden-xs">%s</span>' % _('Fixed')
                    break
        else:
            text += '\n%s' % _('Parent device not found')
    except Device.DoesNotExist:
        pass
    return {
        'status': status,
        'dat': text
    }


@login_required
@only_admins
def fix_port_conflict(request, group_id, device_id, port_id):
    dev_group = get_object_or_404(Group, pk=group_id)
    device = get_object_or_404(Device, pk=device_id)
    port = get_object_or_404(Port, pk=port_id)
    abons = Abon.objects.filter(device__id=device_id, dev_port__id=port_id)
    return render(request, 'devapp/manage_ports/fix_abon_device.html', {
        'abons': abons,
        'group': dev_group,
        'device': device,
        'port': port
    })


class OnDeviceMonitoringEvent(global_base_views.SecureApiView):
    #
    # Api view for monitoring devices
    #
    http_method_names = ('get',)

    @method_decorator(json_view)
    def get(self, request):
        try:
            dev_ip = request.GET.get('dev_ip')
            dev_status = request.GET.get('status')

            if dev_ip is None or dev_ip == '':
                return {'text': 'ip does not passed'}

            if not re.match(IP_ADDR_REGEX, dev_ip):
                return {'text': 'ip address %s is not valid' % dev_ip}

            device_down = Device.objects.filter(ip_address=dev_ip).defer(
                'extra_data'
            ).first()
            if device_down is None:
                return {'text': 'Devices with ip %s does not exist' % dev_ip}

            if dev_status == 'UP':
                device_down.status = 'up'
                notify_text = 'Device %(device_name)s is up'
            elif dev_status == 'DOWN':
                device_down.status = 'dwn'
                notify_text = 'Device %(device_name)s is down'
            elif dev_status == 'UNREACHABLE':
                device_down.status = 'unr'
                notify_text = 'Device %(device_name)s is unreachable'
            else:
                device_down.status = 'und'
                notify_text = 'Device %(device_name)s getting undefined status code'

            device_down.save(update_fields=('status',))

            if not device_down.is_noticeable:
                return {
                    'text': 'Notification for %s is unnecessary' %
                            device_down.ip_address or device_down.comment
                }

            recipients = UserProfile.objects.get_profiles_by_group(
                device_down.group.pk
            ).filter(flags=UserProfile.flags.notify_mon)

            user_ids = tuple(recipient.pk for recipient in recipients.only('pk').iterator())
            text = gettext(notify_text) % {
                'device_name': "%s(%s) %s" % (
                    device_down.ip_address or '',
                    device_down.mac_addr,
                    device_down.comment
                )
            }
            #multicast_email_notify.delay(msg_text=text, account_ids=user_ids)
            multicast_viber_notify.delay(None, account_id_list=user_ids, message_text=text)
            return {
                'text': 'notification successfully sent'
            }
        except (ValueError, OperationalError) as e:
            return {
                'text': str(e)
            }


@hash_auth_view
def nagios_objects_conf(request):
    def getconf(device_instance: Device):
        try:
            config = device_instance.generate_config_template()
            if config is not None:
                return config
        except DeviceImplementationError:
            pass

    devices_queryset = Device.objects.exclude(
        Q(mac_addr=None) | Q(ip_address='127.0.0.1')) \
        .select_related('parent_dev') \
        .only('ip_address', 'comment', 'parent_dev')
    confs = map(getconf, devices_queryset)
    confs = (c for c in confs if c is not None)
    response = HttpResponse(''.join(confs), content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename="objects.cfg"'
    return response


class DevicesGetListView(global_base_views.SecureApiView):
    http_method_names = ('get',)

    @method_decorator(json_view)
    def get(self, request, *args, **kwargs):
        from netaddr import EUI
        device_type = request.GET.get('type')
        dev_types = tuple(dt[0] for dt in Device.DEVICE_TYPES)
        if device_type not in dev_types:
            devs = Device.objects.all()
        else:
            devs = Device.objects.filter(devtype=device_type)
        res = devs.defer('man_passw', 'group', 'parent_dev',
                         'extra_data').values()
        for r in res:
            if isinstance(r['mac_addr'], EUI):
                r['mac_addr'] = int(r['mac_addr'])
        return list(res)


@login_required
@only_admins
@json_view
def register_device(request, group_id: int, device_id: int):
    def format_msg(msg: str, icon: str):
        return ' '.join((
            '<span class="glyphicon glyphicon-%s"></span>' % icon,
            '<span class="hidden-xs">%s</span>' % msg
        ))

    device = get_object_or_404(Device, pk=device_id)
    status = 1
    try:
        device.register_device()
        status = 0
    except expect_scripts.OnuZteRegisterError:
        text = format_msg(gettext('Unregistered onu not found'), 'eye-close')
    except expect_scripts.ZteOltLoginFailed:
        text = format_msg(
            gettext('Wrong login or password for telnet access'),
            'lock'
        )
    except (
            ConnectionRefusedError, expect_scripts.ZteOltConsoleError,
            expect_scripts.ExpectValidationError, expect_scripts.ZTEFiberIsFull
    ) as e:
        text = format_msg(e, 'exclamation-sign')
    except DeviceImplementationError as e:
        text = format_msg(str(e), 'wrench')
    except ProcessLocked:
        text = format_msg(
            gettext('Process locked by another process'),
            'time'
        )
    else:
        text = format_msg(msg='ok', icon='ok')
    return {
        'status': status,
        'dat': text,
        'extra_form_val': device.snmp_extra
    }
