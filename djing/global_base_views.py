from ipaddress import ip_address, ip_network
from json import dumps

from django.core.exceptions import ImproperlyConfigured
from django.utils.decorators import method_decorator
from django.views.generic.base import View
from django.http.response import HttpResponseForbidden, Http404, HttpResponseRedirect, HttpResponse
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.views.generic import ListView
from django.core.paginator import InvalidPage, EmptyPage
from djing.lib.decorators import hash_auth_view


class RedirectWhenError(Exception):
    def __init__(self, url, failed_message=None):
        self.url = url
        if failed_message is not None:
            self.message = failed_message

    def __str__(self):
        return self.message or ''


@method_decorator(hash_auth_view, name='dispatch')
class HashAuthView(View):

    def __init__(self, *args, **kwargs):
        api_auth_secret = getattr(settings, 'API_AUTH_SECRET')
        if api_auth_secret is None or api_auth_secret == 'your api secret':
            raise ImproperlyConfigured('You must specified API_AUTH_SECRET in settings')
        else:
            super(HashAuthView, self).__init__(*args, **kwargs)


class AuthenticatedOrHashAuthView(HashAuthView):

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.is_admin:
                return View.dispatch(self, request, *args, **kwargs)
            else:
                return HttpResponseRedirect('client_side:home')
        else:
            return HashAuthView.dispatch(self, request, *args, **kwargs)


class AllowedSubnetMixin(object):
    def dispatch(self, request, *args, **kwargs):
        """
        Check if user ip in allowed subnet.
        Return 403 denied otherwise.
        """
        ip = ip_address(request.META.get('REMOTE_ADDR'))
        api_auth_subnet = getattr(settings, 'API_AUTH_SUBNET')
        if type(api_auth_subnet) is str:
            if ip in ip_network(api_auth_subnet):
                return super(AllowedSubnetMixin, self).dispatch(request, *args, **kwargs)
        try:
            for subnet in api_auth_subnet:
                if ip in ip_network(subnet, strict=False):
                    return super(AllowedSubnetMixin, self).dispatch(request, *args, **kwargs)
        except TypeError:
            if ip in ip_network(str(api_auth_subnet)):
                return super(AllowedSubnetMixin, self).dispatch(request, *args, **kwargs)
        return HttpResponseForbidden('Access Denied')


class SecureApiView(AllowedSubnetMixin, HashAuthView):
    pass


class OrderingMixin(object):
    """
    Ordering result object list by @order_by variable in get request.
    For example url?order_by=username orders objects by username.
    @dir - direction of ordering. down or up.
    @order_by - ordering field name
    """

    def get_context_data(self, **kwargs):
        context = super(OrderingMixin, self).get_context_data(**kwargs)
        context['order_by'] = self.request.GET.get('order_by')
        return context

    def get_ordering(self):
        direction = self.request.GET.get('dir')
        order_by = self.request.GET.get('order_by')
        dfx = ''
        if direction == 'down':
            dfx = '-'
        if order_by:
            return "%s%s" % (dfx, order_by)


class RedirectWhenErrorMixin(object):
    def get(self, request, *args, **kwargs):
        try:
            return super(RedirectWhenErrorMixin, self).get(request, *args, **kwargs)
        except RedirectWhenError as e:
            if request.is_ajax():
                return HttpResponse(dumps({
                    'url': e.url,
                    'text': e.message or ''
                }))
            else:
                return HttpResponseRedirect(e.url)


class BaseListWithFiltering(RedirectWhenErrorMixin, ListView):
    """
    When queryset contains filter and pagination than data may be missing,
    and original code is raising 404 error. We want to redirect without pagination.
    """

    def paginate_queryset(self, queryset, page_size):
        paginator = self.get_paginator(
            queryset, page_size, orphans=self.get_paginate_orphans(),
            allow_empty_first_page=self.get_allow_empty())
        page_kwarg = self.page_kwarg
        page = self.kwargs.get(page_kwarg) or self.request.GET.get(page_kwarg) or 1
        try:
            page_number = int(page)
        except ValueError:
            if page == 'last':
                page_number = paginator.num_pages
            else:
                raise Http404(_("Page is not 'last', nor can it be converted to an int."))
        try:
            page = paginator.page(page_number)
            return paginator, page, page.object_list, page.has_other_pages()
        except EmptyPage:
            # remove pagination from url
            url = self.request.GET.copy()
            del url[self.page_kwarg]
            raise RedirectWhenError("%s?%s" % (self.request.path, url.urlencode()),
                                    _('Filter does not contains data, filter without pagination'))
        except InvalidPage as e:
            raise Http404(_('Invalid page (%(page_number)s): %(message)s') % {
                'page_number': page_number,
                'message': str(e)
            })


class OrderedFilteredList(OrderingMixin, BaseListWithFiltering):
    paginate_by = getattr(settings, 'PAGINATION_ITEMS_PER_PAGE', 10)
