from django.contrib import admin

from guesty.models import RawEvent
from util.admin import ModelAdmin


@admin.register(RawEvent)
class RawEventAdmin(ModelAdmin):
  list_display = (
      'event_name', 'created_at', 'handled_at', 'reservation')
  list_filter = ('event_name',)
