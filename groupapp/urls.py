from django.urls import path
from . import views

app_name = 'groupapp'

urlpatterns = [
    path('', views.GroupListView.as_view(), name='group_list'),
    path('add/', views.AddGroupView.as_view(), name='add'),
    path('<int:group_id>/edit/', views.EditGroupView.as_view(), name='edit'),
    path('<int:group_id>/del/', views.DeleteGroupView.as_view(), name='del')
]
