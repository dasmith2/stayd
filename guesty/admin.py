from django.contrib import admin

from guesty.models import RawEvent


class RawEventAdmin(admin.ModelAdmin):
  list_display = ('event_name', 'created_at', 'handled_at', 'reservation')


admin.site.register(RawEvent, RawEventAdmin)
