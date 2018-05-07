from django.contrib import admin
from rentals.models import Rental, Owner
from owner_payouts.models import PayoutRule


class RentalAdmin(admin.ModelAdmin):
  list_display = ('airbnb_address_scrape', 'owner')


class PayoutRuleInline(admin.TabularInline):
  model = PayoutRule


class OwnerAdmin(admin.ModelAdmin):
  list_display = ('name', 'email')
  # The whole point of creating an owner is to pay them. So even though
  # developers would expect the PayoutRule in the owner_payouts app,
  # it kind of makes sense to leave owners with rentals and modify the rules
  # here.
  inlines = [PayoutRuleInline]


admin.site.register(Rental, RentalAdmin)
admin.site.register(Owner, OwnerAdmin)
