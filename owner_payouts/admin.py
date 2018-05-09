from django.contrib import admin

from owner_payouts.models import OwnerPayout


class OwnerPayoutAdmin(admin.ModelAdmin):
  list_display = [
      'owner_payout_id', 'who_to_pay_email', 'amount',
      'green_light', 'when_should', 'when_did', 'payout_status']
  ordering = ['when_should']

  def owner_payout_id(self, obj):
    return obj.public_id
  owner_payout_id.short_description = 'ID'

  def who_to_pay_email(self, obj):
    return obj.who_to_pay.email

  who_to_pay_email.short_description = 'Who to pay'


admin.site.register(OwnerPayout, OwnerPayoutAdmin)
