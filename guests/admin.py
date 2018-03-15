from django.contrib import admin
from guests.models import Guest


class GuestAdmin(admin.ModelAdmin):
  list_display = [
      'full_name', 'joined_airbnb_when', 'airbnb_says_theyre_from', 'phone']


admin.site.register(Guest, GuestAdmin)
