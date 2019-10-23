from django.contrib import admin

from .models import UserProfile, UserProfileLog

admin.site.register(UserProfile)
admin.site.register(UserProfileLog)
