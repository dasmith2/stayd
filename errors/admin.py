from django.contrib import admin

from errors.models import StaydError, StaydNotification
from util.admin import ModelAdmin


def mark_fixed(modeladmin, request, queryset):
  queryset.update(fixed=True)


mark_fixed.short_description = 'Mark fixed'


@admin.register(StaydError)
class StaydErrorAdmin(ModelAdmin):
  list_display = (
      'title', 'fixed', 'latest_at', 'created_at', 'count', 'error_message',
      'to')
  ordering = ('-latest_at', '-created_at',)
  actions = [mark_fixed]


@admin.register(StaydNotification)
class StaydNotificationAdmin(ModelAdmin):
  list_display = ('title', 'created_at', 'latest_at', 'count', 'message', 'to')
