from django.contrib import admin

from netsuite.models.category_by_channel import CategoryByChannel
from netsuite.models.location import Location


@admin.register(CategoryByChannel)
class CategoryByChannelAdmin(admin.ModelAdmin):
  list_display = [
      'channel', 'sales_category_name', 'sales_category_id',
      'fee_category_name', 'fee_category_id']


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
  def nickname(self, instance):
    return instance.rental.nickname
  nickname.short_description = 'Location Name'

  list_display = ['nickname', 'location_id']
