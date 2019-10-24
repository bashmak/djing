from django.urls import path

from . import views

app_name = 'tasks'

urlpatterns = [
    path('', views.NewTasksView.as_view(), name='home'),
    path('<int:task_id>/', views.TaskUpdateView.as_view(), name='edit'),
    path('<int:task_id>/delete/', views.task_delete, name='delete'),
    path('<int:task_id>/fin/', views.task_finish, name='finish'),
    path('<int:task_id>/fail/', views.task_failed, name='fail'),
    path('<int:task_id>/remind/', views.remind, name='remind'),
    path('<int:task_id>/comment/add/', views.NewCommentView.as_view(), name='comment_add'),
    path('<int:task_id>/comment/<int:comment_id>/remove/', views.DeleteCommentView.as_view(),
        name='comment_del'),
    path('add/', views.TaskUpdateView.as_view(), name='add'),
    path('failed/', views.FailedTasksView.as_view(), name='failed_tasks'),
    path('finished/', views.FinishedTaskListView.as_view(), name='finished_tasks'),
    path('own/', views.OwnTaskListView.as_view(), name='own_tasks'),
    path('my/', views.MyTaskListView.as_view(), name='my_tasks'),
    path('all/', views.AllTasksListView.as_view(), name='all_tasks'),
    path('all_new/', views.AllNewTasksListView.as_view(), name='all_new_tasks'),
    path('empty/', views.EmptyTasksListView.as_view(), name='empty_tasks')
]
