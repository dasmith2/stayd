from django.contrib import admin
from django.contrib.auth.models import Group
from reservations.models import Reservation


class ReservationAdmin(admin.ModelAdmin):
  list_display = [
      'channel_reservation_id', 'guest', 'check_in', 'check_out', 'listing',
      'price_per_night', 'night_count', 'total_payin', 'is_paid_in']
  ordering = ('-check_in',)


admin.site.unregister(Group)
admin.site.register(Reservation, ReservationAdmin)
