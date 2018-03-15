from django.contrib import admin
from listings.models import Listing


class ListingAdmin(admin.ModelAdmin):
  list_display = [
      'channel_listing_id', 'channel', 'firefox_profile', 'title',
      'get_address']

  def get_address(self, obj):
    return obj.rental.airbnb_address_scrape

  get_address.short_description = 'Address'


admin.site.register(Listing, ListingAdmin)
