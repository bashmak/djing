from datetime import datetime
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import redirect, get_object_or_404, resolve_url
from django.contrib import messages
from django.views.generic import ListView, CreateView
from django.utils.translation import ugettext as _
from django.conf import settings
from django.views.generic.edit import FormMixin, DeleteView, UpdateView

from guardian.shortcuts import assign_perm
from abonapp.models import Abon
from djing import httpresponse_to_referrer
from djing.lib import safe_int, MultipleException
from djing.lib.decorators import only_admins
from djing.lib.mixins import LoginAdminMixin, LoginAdminPermissionMixin
from .handle import TaskException
from .models import Task, ExtraComment
from .forms import TaskFrm, ExtraCommentForm


# Maked compatible

class NewTasksView(LoginAdminPermissionMixin, ListView):
    """
    Show new tasks
    """
    http_method_names = ('get',)
    paginate_by = getattr(settings, 'PAGINATION_ITEMS_PER_PAGE', 10)
    template_name = 'tasks/tasklist.html'
    context_object_name = 'tasks'
    permission_required = 'tasks.view_task'

    def get_queryset(self):
        return Task.objects.filter(
            recipients=self.request.user, task_state=0
        ).annotate(
            comment_count=Count('extracomment')
        ).select_related(
            'abon', 'abon__street', 'abon__group', 'author'
        )


class FailedTasksView(NewTasksView):
    """
    Show crashed tasks
    """
    template_name = 'tasks/tasklist_failed.html'
    context_object_name = 'tasks'

    def get_queryset(self):
        return Task.objects.filter(
            recipients=self.request.user, task_state=1
        ).select_related(
            'abon', 'abon__street', 'abon__group', 'author'
        )


class FinishedTaskListView(NewTasksView):
    template_name = 'tasks/tasklist_finish.html'

    def get_queryset(self):
        return Task.objects.filter(
            recipients=self.request.user, task_state=2
        ).select_related(
            'abon', 'abon__street', 'abon__group', 'author'
        )


class OwnTaskListView(NewTasksView):
    template_name = 'tasks/tasklist_own.html'

    def get_queryset(self):
        # Attached and not finished tasks
        return Task.objects.filter(
            author=self.request.user
        ).exclude(task_state=2).select_related(
            'abon', 'abon__street', 'abon__group'
        )


class MyTaskListView(NewTasksView):
    template_name = 'tasks/tasklist.html'

    def get_queryset(self):
        # Tasks in which I participated
        return Task.objects.filter(
            recipients=self.request.user
        ).select_related(
            'abon', 'abon__street', 'abon__group', 'author'
        )


class AllTasksListView(LoginAdminMixin, LoginRequiredMixin, ListView):
    http_method_names = ('get',)
    paginate_by = getattr(settings, 'PAGINATION_ITEMS_PER_PAGE', 10)
    template_name = 'tasks/tasklist_all.html'
    context_object_name = 'tasks'
    permission_required = 'tasks.can_viewall'

    def get_queryset(self):
        return Task.objects.annotate(
            comment_count=Count('extracomment')
        ).select_related(
            'abon', 'abon__street', 'abon__group', 'author'
        )


class AllNewTasksListView(AllTasksListView):

    def get_queryset(self):
        return super(AllNewTasksListView, self).get_queryset().filter(task_state=0)


class EmptyTasksListView(NewTasksView):
    template_name = 'tasks/tasklist_empty.html'

    def get_queryset(self):
        return Task.objects.annotate(
            reccount=Count('recipients')
        ).filter(reccount__lt=1)


@login_required
@only_admins
@permission_required('tasks.delete_task')
def task_delete(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    # prevent to delete task that assigned to me
    if request.user.is_superuser or request.user not in task.recipients.all():
        task.delete()
    else:
        messages.warning(
            request, _('You cannot delete task that assigned to you')
        )
    return redirect('tasks:home')


class TaskUpdateView(LoginAdminMixin, UpdateView):
    http_method_names = ('get', 'post')
    template_name = 'tasks/add_edit_task.html'
    form_class = TaskFrm
    context_object_name = 'task'

    def get_object(self, queryset=None):
        task_id = safe_int(self.kwargs.get('task_id'))
        if task_id == 0:
            uname = self.request.GET.get('uname')
            if uname:
                self.selected_abon = Abon.objects.get(username=uname)
            return
        else:
            task = get_object_or_404(Task, pk=task_id)
            self.selected_abon = task.abon
            return task

    def dispatch(self, request, *args, **kwargs):
        task_id = safe_int(self.kwargs.get('task_id', 0))
        if task_id == 0:
            if not request.user.has_perm('tasks.add_task'):
                raise PermissionDenied
        else:
            if not request.user.has_perm('tasks.change_task'):
                raise PermissionDenied

        # check if new task with user already exists
        uname = request.GET.get('uname')
        if uname and self.kwargs.get('task_id') is None:
            exists_task = Task.objects.filter(abon__username=uname, task_state=0)
            if exists_task.exists():
                messages.info(request, _('New task with this user already exists.'
                                         ' You are redirected to it.'))
                return redirect('tasks:edit', exists_task.first().pk)

        try:
            return super(TaskUpdateView, self).dispatch(request, *args, **kwargs)
        except TaskException as e:
            messages.error(request, e)
        return httpresponse_to_referrer(request)

    def get_form_kwargs(self):
        kwargs = super(TaskUpdateView, self).get_form_kwargs()
        if hasattr(self, 'selected_abon'):
            kwargs.update({'initial_abon': self.selected_abon})
        return kwargs

    def form_valid(self, form):
        # check if new task with picked user already exists
        if form.cleaned_data['task_state'] == 0 and self.kwargs.get('task_id') is None:
            exists_task = Task.objects.filter(abon=form.cleaned_data['abon'], task_state=0)
            if exists_task.exists():
                messages.info(self.request, _('New task with this user already exists.'
                                              ' You are redirected to it.'))
                return redirect('tasks:edit', exists_task.first().pk)

        try:
            self.object = form.save()
            if self.object.author is None:
                self.object.author = self.request.user
                self.object.save(update_fields=('author',))
            task_id = safe_int(self.kwargs.get('task_id', 0))
            if task_id == 0:
                log_text = _('Task has successfully created')
            else:
                log_text = _('Task has changed successfully')
            messages.add_message(self.request, messages.SUCCESS, log_text)
            self.object.send_notification()
        except MultipleException as e:
            for err in e.err_list:
                messages.add_message(self.request, messages.WARNING, err)
        except TaskException as e:
            messages.add_message(self.request, messages.ERROR, e)
        return FormMixin.form_valid(self, form)

    def get_context_data(self, **kwargs):
        if hasattr(self, 'selected_abon'):
            selected_abon = self.selected_abon
        else:
            selected_abon = None

        now_date = datetime.now().date()
        task = self.object
        if task:
            if task.out_date > now_date:
                time_diff = "%s: %s" % (_('time left'), (task.out_date - now_date))
            else:
                time_diff = _("Expired timeout -%(time_left)s") % {
                    'time_left': (now_date - task.out_date)
                }
        else:
            time_diff = None

        context = {
            'selected_abon': selected_abon,
            'time_diff': time_diff,
            'comments': ExtraComment.objects.filter(task=task),
            'comment_form': ExtraCommentForm()
        }
        context.update(kwargs)
        return super(TaskUpdateView, self).get_context_data(**context)

    def get_success_url(self):
        task_id = safe_int(self.kwargs.get('task_id'))
        if task_id == 0:
            return resolve_url('tasks:own_tasks')
        else:
            return resolve_url('tasks:edit', task_id)

    def form_invalid(self, form):
        messages.add_message(
            self.request, messages.ERROR,
            _('fix form errors')
        )
        return super(TaskUpdateView, self).form_invalid(form)


@login_required
@only_admins
def task_finish(request, task_id):
    try:
        task = get_object_or_404(Task, id=task_id)
        task.finish(request.user)
        task.send_notification()
    except MultipleException as errs:
        for err in errs.err_list:
            messages.add_message(request, messages.constants.ERROR, err)
    except TaskException as e:
        messages.error(request, e)
    return redirect('tasks:home')


@login_required
@only_admins
def task_failed(request, task_id):
    try:
        task = get_object_or_404(Task, id=task_id)
        task.do_fail(request.user)
        task.send_notification()
    except TaskException as e:
        messages.error(request, e)
    return redirect('tasks:home')


@login_required
@only_admins
@permission_required('tasks.can_remind')
def remind(request, task_id):
    try:
        task = get_object_or_404(Task, id=task_id)
        task.save(update_fields=('task_state',))
        task.send_notification()
        messages.success(request, _('Task has been reminded'))
    except MultipleException as errs:
        for err in errs.err_list:
            messages.add_message(request, messages.constants.ERROR, err)
    except TaskException as e:
        messages.error(request, e)
    return redirect('tasks:home')


class NewCommentView(LoginAdminMixin, LoginRequiredMixin, CreateView):
    form_class = ExtraCommentForm
    model = ExtraComment
    http_method_names = ('get', 'post')
    permission_required = 'tasks.add_extracomment'

    def form_valid(self, form):
        self.task = get_object_or_404(Task, pk=self.kwargs.get('task_id'))
        self.object = form.make_save(
            author=self.request.user,
            task=self.task
        )
        author = self.object.author
        assign_perm('tasks.change_extracomment', author, self.object)
        assign_perm('tasks.delete_extracomment', author, self.object)
        assign_perm('tasks.view_extracomment', author, self.object)
        return FormMixin.form_valid(self, form)


class DeleteCommentView(LoginAdminPermissionMixin, DeleteView):
    model = ExtraComment
    pk_url_kwarg = 'comment_id'
    http_method_names = ('get', 'post')
    template_name = 'tasks/comments/extracomment_confirm_delete.html'
    permission_required = 'tasks.delete_extracomment'

    def get_context_data(self, **kwargs):
        context = {
            'task_id': self.kwargs.get('task_id')
        }
        context.update(kwargs)
        return super(DeleteCommentView, self).get_context_data(**context)

    def get_success_url(self):
        task_id = self.kwargs.get('task_id')
        return resolve_url('tasks:edit', task_id)
