from django.contrib import admin

from errors.models import StaydError


class StaydErrorAdmin(admin.ModelAdmin):
  list_display = ('title', 'fixed', 'created_at', 'count', 'error_message')
  ordering = ('-created_at',)


admin.site.register(StaydError, StaydErrorAdmin)
