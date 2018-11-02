from django.contrib import admin

from errors.models import StaydError, StaydNotification


def mark_fixed(modeladmin, request, queryset):
  queryset.update(fixed=True)


mark_fixed.short_description = 'Mark fixed'


@admin.register(StaydError)
class StaydErrorAdmin(admin.ModelAdmin):
  list_display = (
      'title', 'fixed', 'created_at', 'count', 'error_message', 'to')
  ordering = ('-created_at',)
  actions = [mark_fixed]


@admin.register(StaydNotification)
class StaydNotificationAdmin(admin.ModelAdmin):
  list_display = ('title', 'created_at', 'latest_at', 'count', 'message', 'to')
