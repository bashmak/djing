from kombu.exceptions import OperationalError
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from django.utils.translation import gettext_lazy as _, gettext

from abonapp.models import AbonLog, InvoiceForPayment, Abon
from abonapp.tasks import customer_nas_command
from djing.lib.decorators import json_view
from tariff_app.models import Tariff
from tasks.models import Task
from djing.lib import LogicError
from gw_app.nas_managers import NasFailedResult, NasNetworkError


@login_required
def home(request):
    num_active_tasks = Task.objects.filter(
        abon=request.user, state=0
    ).count()
    return render(request, 'clientsideapp/index.html', {
        'num_active_tasks': num_active_tasks
    })


@login_required
def pays(request):
    pay_history = AbonLog.objects.filter(abon=request.user).order_by('-id')
    return render(request, 'clientsideapp/pays.html', {
        'pay_history': pay_history
    })


@login_required
def services(request):
    try:
        abon = request.user
        all_tarifs = Tariff.objects.get_tariffs_by_group(
            abon.group.pk
        )# .filter(is_admin=False)
        current_service = abon.active_tariff()
    except Abon.DoesNotExist:
        all_tarifs = None
        current_service = None
    return render(request, 'clientsideapp/services.html', {
        'tarifs': all_tarifs,
        'current_service': current_service
    })


@login_required
def buy_service(request, srv_id):
    abon = request.user
    service = get_object_or_404(Tariff, pk=srv_id)
    try:
        if request.method == 'POST':
            abon.pick_tariff(
                tariff=service, author=abon,
                comment=_("Buy the service via user side, service '%s'") % service
            )
            customer_nas_command.delay(abon.pk, 'sync')
            messages.success(
                request,
                _("The service '%s' was successfully activated") % service.title
            )
        else:
            current_service = abon.active_tariff()
            return render(request, 'clientsideapp/modal_service_buy.html', {
                'service': service,
                'current_service': current_service.tariff
                if current_service is not None else None
            })
    except LogicError as e:
        messages.error(request, e)
    except NasFailedResult as e:
        messages.error(request, e)
    except OperationalError:
        pass
    return redirect('client_side:services')


@login_required
def debts_list(request):
    debts = InvoiceForPayment.objects.filter(abon=request.user)
    return render(request, 'clientsideapp/debts.html', {
        'debts': debts
    })


@login_required
@transaction.atomic
def debt_buy(request, d_id):
    debt = get_object_or_404(InvoiceForPayment, id=d_id)
    abon = request.user
    if request.method == 'POST':
        try:
            sure = request.POST.get('sure')
            if sure != 'on':
                raise LogicError(
                    _("Are you not sure that you want buy the service?")
                )
            if abon.ballance < debt.amount:
                raise LogicError(_('Your account have not enough money'))

            amount = -debt.amount
            abon.add_ballance(
                None, amount,
                comment=gettext('%(username)s paid the debt %(amount).2f') % {
                    'username': abon.get_full_name(),
                    'amount': amount
                }
            )
            abon.save(update_fields=('ballance',))
            debt.set_ok()
            debt.save(update_fields=('status', 'date_pay'))
            return redirect('client_side:debts')
        except LogicError as e:
            messages.error(request, e)
        except NasFailedResult as e:
            messages.error(request, e)
        except NasNetworkError as e:
            messages.error(request, e)
    return render(request, 'clientsideapp/debt_buy.html', {
        'debt': debt,
        'amount': debt.amount,
        'ballance_after': abon.ballance - debt.amount
    })


@login_required
def task_history(request):
    tasks = Task.objects.filter(abon=request.user)
    return render(request, 'clientsideapp/tasklist.html', {
        'tasks': tasks
    })


@login_required
@json_view
def set_auto_continue_service(request):
    checked = request.GET.get('checked')
    checked = checked == 'true'
    abon = request.user
    abon.autoconnect_service = checked
    abon.save(update_fields=('autoconnect_service',))
    return {
        'status': 0
    }
