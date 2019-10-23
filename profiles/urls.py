from django.urls import path, re_path
from django.contrib.auth.views import LogoutView

from . import views

app_name = 'account_app'

urlpatterns = [
    path('', views.AccountsListView.as_view(), name='accounts_list'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='acc_app:login'), name='logout'),
    path('login_by_location/', views.location_login, name='llogin'),

    path('add/', views.create_profile, name='create_profile'),

    path('settings/', views.UpdateSelfAccount.as_view(), name='setup_info'),
    path('settings/change_ava/', views.AvatarUpdateView.as_view(), name='setup_avatar'),

    path('<int:uid>/', views.ProfileShowDetailView.as_view(), name='other_profile'),
    path('<int:uid>/edit/', views.UpdateAccount.as_view(), name='edit_profile'),
    path('<int:uid>/perms/', views.PermsUpdateView.as_view(), name='setup_perms'),
    path('<int:uid>/perms/object/', views.perms_object, name='setup_perms_object'),

    re_path('^(?P<uid>\d+)/perms/object/(?P<klass_name>[a-z_]+\.[a-zA-Z_]+)/$', views.PermissionClassListView.as_view(), name='perms_klasses'),

    re_path('^(?P<uid>\d+)/perms/object/(?P<klass_name>[a-z_]+\.[a-zA-Z_]+)/(?P<obj_id>\d+)/$', views.perms_edit, name='perms_edit'),

    path('<int:uid>/del/', views.delete_profile, name='delete_profile'),

    path('<int:uid>/user_group_access/', views.set_abon_groups_permission, name='set_abon_groups_permission'),

    path('<int:uid>/manage_responsibility_groups/', views.ManageResponsibilityGroups.as_view(), name='manage_responsibility_groups'),

    path('<int:uid>/actions/', views.ActionListView.as_view(), name='action_log')
]
