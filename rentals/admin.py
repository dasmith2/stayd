from django.contrib import admin
from rentals.models import Rental, Owner, PayoutRule


class RentalAdmin(admin.ModelAdmin):
  list_display = ('airbnb_address_scrape', 'owner')


class PayoutRuleInline(admin.TabularInline):
  model = PayoutRule


class OwnerAdmin(admin.ModelAdmin):
  list_display = ('name', 'email')
  inlines = [PayoutRuleInline]


admin.site.register(Rental, RentalAdmin)
admin.site.register(Owner, OwnerAdmin)
