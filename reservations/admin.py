from django.contrib import admin
from reservations.models import Reservation, ResolutionCategory
from util.admin import ModelAdmin


@admin.register(Reservation)
class ReservationAdmin(ModelAdmin):
  list_display = [
      'channel_id', 'guest', 'check_in', 'check_out', 'rental',
      'channel', 'ideal_payin', 'is_paid_in']
  ordering = ('-check_in',)


@admin.register(ResolutionCategory)
class ResolutionCategory(ModelAdmin):
  list_display = ['name']
