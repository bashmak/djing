import csv
from hashlib import md5

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import DatabaseError, transaction
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, resolve_url
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.utils.translation import ugettext_lazy as _
from xmlview.decorators import xml_view
from djing import lib
from djing.global_base_views import OrderedFilteredList
from djing.lib.mixins import LoginAdminMixin, LoginAdminPermissionMixin
from finapp.forms import PayAllTimeGatewayForm
from finapp.models import AllTimePayLog, PayAllTimeGateway
from abonapp.models import Abon


class AllTimePay(DetailView):
    http_method_names = 'get',
    model = PayAllTimeGateway
    pk_url_kwarg = 'slug'
    slug_url_kwarg = 'pay_slug'

    @staticmethod
    def _bad_ret(err_id, err_description=None):
        now = timezone.now()
        r = {
            'status_code': lib.safe_int(err_id),
            'time_stamp': now.strftime("%d.%m.%Y %H:%M")
        }
        if err_description:
            r.update({'description': err_description})
        return r

    def check_sign(self, data: dict, sign: str) -> bool:
        act = lib.safe_int(data.get('ACT'))
        pay_account = data.get('PAY_ACCOUNT')
        serv_id = data.get('SERVICE_ID')
        pay_id = data.get('PAY_ID')
        md = md5()
        s = '_'.join(
            (str(act), pay_account or '', serv_id or '',
             pay_id or '', self.object.secret)
        )
        md.update(bytes(s, 'utf-8'))
        our_sign = md.hexdigest()
        return our_sign == sign

    @method_decorator(xml_view(root_node='pay-response'))
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        act = lib.safe_int(request.GET.get('ACT'))
        self.current_date = timezone.now().strftime("%d.%m.%Y %H:%M")

        if act <= 0:
            return self._bad_ret(-101, 'ACT must be more than 0')
        sign = request.GET.get('SIGN')
        if not sign:
            return self._bad_ret(-101, 'SIGN not passed')
        if not self.check_sign(request.GET, sign.lower()):
            return self._bad_ret(-101, 'Bad sign')

        try:
            if act == 1:
                return self._fetch_user_info(request.GET)
            elif act == 4:
                return self._make_pay(request.GET)
            elif act == 7:
                return self._check_pay(request.GET)
            else:
                return self._bad_ret(-101, 'ACT is not passed')
        except Abon.DoesNotExist:
            return self._bad_ret(-40, 'Account does not exist')
        except DatabaseError:
            return self._bad_ret(-90)
        except AllTimePayLog.DoesNotExist:
            return self._bad_ret(-10)
        except AttributeError:
            return self._bad_ret(-101)

    def _fetch_user_info(self, data: dict):
        pay_account = data.get('PAY_ACCOUNT')
        abon = Abon.objects.get(username=pay_account)
        fio = abon.fio
        ballance = float(abon.ballance)
        return {
            'balance': ballance,
            'name': fio,
            'account': pay_account,
            'service_id': self.object.service_id,
            'min_amount': 10.0,
            'max_amount': 5000,
            'status_code': 21,
            'time_stamp': self.current_date
        }

    def _make_pay(self, data: dict):
        trade_point = lib.safe_int(data.get('TRADE_POINT'))
        receipt_num = lib.safe_int(data.get('RECEIPT_NUM'))
        pay_account = data.get('PAY_ACCOUNT')
        pay_id = data.get('PAY_ID')
        pay_amount = lib.safe_float(data.get('PAY_AMOUNT'))
        abon = Abon.objects.get(username=pay_account)
        pays = AllTimePayLog.objects.filter(pay_id=pay_id)
        if pays.exists():
            return self._bad_ret(-100, 'Pay already exists')

        with transaction.atomic():
            abon.add_ballance(
                None, pay_amount,
                comment='%s %.2f' % (self.object.title, pay_amount)
            )
            abon.save(update_fields=('ballance',))

            AllTimePayLog.objects.create(
                pay_id=pay_id,
                summ=pay_amount,
                abon=abon,
                trade_point=trade_point,
                receipt_num=receipt_num,
                pay_gw=self.object
            )
        return {
            'pay_id': pay_id,
            'service_id': data.get('SERVICE_ID'),
            'amount': pay_amount,
            'status_code': 22,
            'time_stamp': self.current_date
        }

    def _check_pay(self, data: dict):
        pay_id = data.get('PAY_ID')
        pay = AllTimePayLog.objects.get(pay_id=pay_id)
        return {
            'status_code': 11,
            'time_stamp': self.current_date,
            'transaction': {
                'pay_id': pay_id,
                'service_id': data.get('SERVICE_ID'),
                'amount': pay.summ,
                'status': 111,
                'time_stamp': pay.date_add.strftime("%d.%m.%Y %H:%M")
            }
        }


class BasicFinReport(LoginAdminMixin, ListView):
    model = AllTimePayLog
    queryset = AllTimePayLog.objects.by_days()
    template_name = 'finapp/fin_report.html'
    context_object_name = 'logs'

    def get(self, request, *args, **kwargs):
        res_format = request.GET.get('f')
        if res_format == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="report.csv"'
            writer = csv.writer(response, quoting=csv.QUOTE_NONNUMERIC)
            for row in self.object_list:
                writer.writerow(
                    (row['summ'], row['pay_date'].strftime('%Y-%m-%d'))
                )
            return response
        return super().get(request, *args, **kwargs)


class PayHistoryListView(LoginAdminMixin, PermissionRequiredMixin,
                         OrderedFilteredList):
    permission_required = 'groupapp.view_group'
    context_object_name = 'pay_history'
    template_name = 'finapp/payHistory.html'
    model = AllTimePayLog

    def get_queryset(self):
        pay_history = AllTimePayLog.objects.filter(
            pay_gw__slug=self.kwargs.get('pay_slug')
        ).select_related('abon__group').order_by('-date_add')
        return pay_history

    def get_context_data(self, **kwargs):
        context = {
            'pay_gw': get_object_or_404(PayAllTimeGateway, slug=self.kwargs.get('pay_slug'))
        }
        context.update(kwargs)
        return super(PayHistoryListView, self).get_context_data(**context)


class AddAllTimeGateway(LoginAdminMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'finapp.add_payalltimegateway'
    model = PayAllTimeGateway
    form_class = PayAllTimeGatewayForm
    success_url = reverse_lazy('finapp:alltime_gateways_list')

    def form_valid(self, form):
        messages.success(self.request, _('New pay gateway created successfully'))
        return super(AddAllTimeGateway, self).form_valid(form)


class AllTimeGatewaysListView(LoginAdminPermissionMixin, ListView):
    permission_required = 'finapp.view_payalltimegateway'
    model = PayAllTimeGateway
    queryset = PayAllTimeGateway.objects.annotate(
        pays_count=Count('alltimepaylog')
    )


class EditPayUpdateView(LoginAdminPermissionMixin, UpdateView):
    permission_required = 'finapp.change_payalltimegateway'
    model = PayAllTimeGateway
    form_class = PayAllTimeGatewayForm
    pk_url_kwarg = 'slug'
    slug_url_kwarg = 'pay_slug'

    def get_success_url(self):
        return resolve_url('finapp:edit_pay_gw', self.object.slug)

    def form_valid(self, form):
        messages.success(self.request, _('Payment gateway successfully updated'))
        return super(EditPayUpdateView, self).form_valid(form)
