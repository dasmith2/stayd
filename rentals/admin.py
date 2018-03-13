from django.contrib import admin
from rentals.models import Host


class HostAdmin(admin.ModelAdmin):
  list_display = ['name']
  ordering = ['name']


admin.site.register(Host, HostAdmin)
