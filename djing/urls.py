from django.urls import path, include
from django.conf import settings

from .views import home

urlpatterns = [
    path('', home),
    path('accounts/', include('profiles.urls', namespace='acc_app')),
    path('abons/', include('abonapp.urls', namespace='abonapp')),
    path('tarifs/', include('tariff_app.urls', namespace='tarifs')),
    path('search/', include('searchapp.urls', namespace='searchapp')),
    path('dev/', include('devapp.urls', namespace='devapp')),
    # path('map/', include('mapapp.urls', namespace='mapapp')),
    path('statistic/', include('traf_stat.urls', namespace='traf_stat')),
    path('tasks/', include('tasks.urls', namespace='tasks')),
    path('client/', include('clientsideapp.urls', namespace='client_side')),
    path('msg/', include('msg_app.urls', namespace='msg_app')),
    path('groups/', include('groupapp.urls', namespace='groupapp')),
    path('ip_pool/', include('ip_pool.urls', namespace='ip_pool')),
    path('messenger/', include('messenger.urls', namespace='messenger')),
    path('gw/', include('gw_app.urls', namespace='gw_app')),
    path('new_customers/', include('new_customers.urls', namespace='new_customers')),
    path('fin/', include('finapp.urls', namespace='finapp')),
    path('docs/', include('docsapp.urls', namespace='docsapp'))

    # Switch language
    #path(r'i18n/', include('django.conf.urls.i18n')),

]

if settings.DEBUG:
    from django.conf.urls.static import static
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    from django.contrib import admin

    urlpatterns.extend(static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT))
    urlpatterns.extend(staticfiles_urlpatterns())
    urlpatterns.append(path('admin/', admin.site.urls))
