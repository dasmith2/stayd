from django.contrib import admin
from listings.models import Listing, Airvatar


class AirvatarAdmin(admin.ModelAdmin):
  list_display = [
      'name',
      'ip',
      'port',
      'gmail_address',
      'gmail_password',
      'airbnb_password']
  prepopulated_fields = {"name_slug": ("name",)}


class ListingAdmin(admin.ModelAdmin):
  list_display = [
      'channel_listing_id', 'channel', 'airvatar', 'title',
      'get_address']

  def get_address(self, obj):
    return obj.rental.airbnb_address_scrape

  get_address.short_description = 'Address'


admin.site.register(Airvatar, AirvatarAdmin)
admin.site.register(Listing, ListingAdmin)
