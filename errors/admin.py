from django.contrib import admin

from errors.models import StaydError


def mark_fixed(modeladmin, request, queryset):
  queryset.update(fixed=True)


mark_fixed.short_description = 'Mark fixed'


class StaydErrorAdmin(admin.ModelAdmin):
  list_display = ('title', 'fixed', 'created_at', 'count', 'error_message')
  ordering = ('-created_at',)
  actions = [mark_fixed]


admin.site.register(StaydError, StaydErrorAdmin)
