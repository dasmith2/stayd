from django.contrib import admin

from rentals.models import Rental
from front.models import Front


class RentalAdmin(admin.ModelAdmin):
  list_display = ('airbnb_address_scrape', 'owner')


def get_front_channel_choices():
  front = Front()
  for channel in front.get_channels():
    if channel['type'] == 'twilio':
      yield (channel['id'], channel['name'])


admin.site.register(Rental, RentalAdmin)
