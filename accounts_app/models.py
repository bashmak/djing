# -*- coding:utf-8 -*-
import os
from PIL import Image
from bitfield.models import BitField

from jsonfield import JSONField
from django.db import models
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.shortcuts import resolve_url
from group_app.models import Group


# Maked compatible


class MyUserManager(BaseUserManager):
    def create_user(self, telephone, username, password=None):
        """
        Creates and saves a User with the given email, date of
        birth and password.
        """
        if not telephone:
            raise ValueError(_('Users must have an telephone number'))

        user = self.model(
            telephone=telephone,
            username=username,
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, telephone, username, password):
        """
        Creates and saves a superuser with the given email, date of
        birth and password.
        """
        user = self.create_user(telephone,
                                password=password,
                                username=username
                                )
        user.is_admin = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class BaseAccount(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(
        _('profile username'),
        max_length=127,
        unique=True,
        validators=(RegexValidator(r'^\w{1,127}$'),)
    )
    fio = models.CharField(_('fio'), max_length=256)
    birth_day = models.DateField(_('birth day'), auto_now_add=True)
    is_active = models.BooleanField(_('Is active'), default=True)
    is_admin = models.BooleanField(default=False)
    telephone = models.CharField(
        max_length=16,
        verbose_name=_('Telephone'),
        blank=True,
        validators=(RegexValidator(
            getattr(settings, 'TELEPHONE_REGEXP', r'^(\+[7893]\d{10,11})?$')
        ),)
    )

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ('telephone',)

    def get_full_name(self):
        return self.fio if self.fio else self.username

    def get_short_name(self):
        return self.username or self.telephone

    # Use UserManager to get the create_user method, etc.
    objects = MyUserManager()

    @property
    def is_staff(self):
        " Is the user a member of staff?"
        # Simplest possible answer: All admins are staff
        return self.is_admin

    def __str__(self):
        return self.get_full_name()

    class Meta:
        db_table = 'base_accounts'
        ordering = 'username',


class UserProfileLog(models.Model):
    account = models.ForeignKey('UserProfile', on_delete=models.CASCADE, verbose_name=_('Author'))
    # meta_info = JSONField(verbose_name=_('Meta information'))
    ACTION_TYPES = (
        (0, _('Undefined')),
        (1, _('Create user')),
        (2, _('Delete user')),
        (3, _('Create device')),
        (4, _('Delete device')),
        (5, _('Create NAS')),
        (6, _('Delete NAS')),
        (7, _('Create service')),
        (8, _('Delete service'))
    )
    do_type = models.PositiveSmallIntegerField(_('Action type'), default=0, choices=ACTION_TYPES)
    additional_text = models.CharField(_('Additional info'), blank=True, null=True, max_length=512)
    action_date = models.DateTimeField(_('Action date'), auto_now_add=True)

    def __str__(self):
        return self.get_do_type_display()

    class Meta:
        db_table = 'profiles_userprofilelog'
        ordering = '-action_date',
        verbose_name = _('User profile log')
        verbose_name_plural = _('User profile logs')


class UserProfileManager(MyUserManager):
    def get_profiles_by_group(self, group_id):
        return self.filter(responsibility_groups__id__in=(group_id,), is_admin=True, is_active=True)


class UserProfile(BaseAccount):
    avatar = models.ImageField(_('Avatar'), upload_to=os.path.join('user', 'avatar'), null=True, default=None, blank=True)
    email = models.EmailField(default='', blank=True)
    responsibility_groups = models.ManyToManyField(Group, blank=True, verbose_name=_('Responsibility groups'))
    USER_PROFILE_FLAGS = (
        ('notify_task', _('Notification about tasks')),
        ('notify_msg', _('Notification about messages')),
        ('notify_mon', _('Notification from monitoring'))
    )
    flags = BitField(flags=USER_PROFILE_FLAGS, default=0, verbose_name=_('Settings flags'))

    objects = UserProfileManager()

    def get_big_ava(self):
        if self.avatar and os.path.isfile(self.avatar.path):
            return self.avatar.url
        else:
            return getattr(settings, 'DEFAULT_PICTURE', '/static/img/user_ava.gif')

    def get_min_ava(self):
        return self.get_big_ava()

    class Meta:
        db_table = 'profiles_userprofile'
        verbose_name = _('Staff account profile')
        verbose_name_plural = _('Staff account profiles')
        ordering = 'fio',

    def _thumbnail_avatar(self):
        if self.avatar and os.path.isfile(self.avatar.path):
            im = Image.open(self.avatar)
            im.thumbnail((200, 121), Image.ANTIALIAS)
            im.save(self.avatar.path)

    def save(self, *args, **kwargs):
        r = super().save(*args, **kwargs)
        self._thumbnail_avatar()
        return r

    def log(self, request_meta: dict, do_type: int, additional_text=None) -> None:
        """
        Make log about administrator actions.
        :param request_meta: META from django request.
        :param do_type: Choice from UserProfileLog.ACTION_TYPES
        :param additional_text: Additional information for action
        :return: None
        """
        # inf = {
        #     'src_ip': request_meta.get('REMOTE_ADDR'),
        #     'username': request_meta.get('USER'),
        #     'hostname': request_meta.get('HOSTNAME'),
        #     'useragent': request_meta.get('HTTP_USER_AGENT')
        # }
        UserProfileLog.objects.create(
            account=self,
            # meta_info=inf,
            do_type=do_type,
            additional_text=additional_text
        )

    def get_absolute_url(self):
        return resolve_url('acc_app:other_profile', self.pk)
