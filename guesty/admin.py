from django.contrib import admin

from guesty.models import RawEvent


@admin.register(RawEvent)
class RawEventAdmin(admin.ModelAdmin):
  list_display = (
      'event_name', 'created_at', 'handled_at', 'reservation')
