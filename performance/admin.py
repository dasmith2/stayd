from django.contrib import admin

from performance.models import LongRequest


class LongRequestAdmin(admin.ModelAdmin):
  list_display = ('path', 'duration', 'created_at')


admin.site.register(LongRequest, LongRequestAdmin)
