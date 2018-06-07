from django import forms
from django.contrib import admin

from rentals.models import Rental, Airvatar
from front.models import Front


class RentalAdmin(admin.ModelAdmin):
  list_display = ('airbnb_address_scrape', 'owner')


def get_front_channel_choices():
  front = Front()
  for channel in front.get_channels():
    if channel['type'] == 'twilio':
      yield (channel['id'], channel['name'])


class AirvatarAdminForm(forms.ModelForm):
  front_channel = forms.ChoiceField(choices=get_front_channel_choices)

  class Meta:
    model = Airvatar
    exclude = []


class AirvatarAdmin(admin.ModelAdmin):
  form = AirvatarAdminForm
  list_display = [
      'name',
      'ip',
      'port',
      'gmail_address',
      'gmail_password',
      'airbnb_password',
      'front_channel']
  prepopulated_fields = {"name_slug": ("name",)}


admin.site.register(Airvatar, AirvatarAdmin)
admin.site.register(Rental, RentalAdmin)
