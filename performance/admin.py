from django.contrib import admin

from performance.models import LongRequest
from util.admin import ModelAdmin


class LongRequestAdmin(ModelAdmin):
  list_display = ('path', 'duration', 'created_at')


admin.site.register(LongRequest, LongRequestAdmin)
