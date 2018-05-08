from django.contrib import admin
from owner_payouts.models import OwnerPayout


class OwnerPayoutAdmin(admin.ModelAdmin):
  list_display = [
      'owner_payout_id', 'who_to_pay_email', 'amount', 'green_light',
      'when_should', 'when_did', 'owner_payout_status', 'owner_payout_fee']
  ordering = ['when_should']

  def owner_payout_id(self, obj):
    return obj.public_id

  owner_payout_id.short_description = 'ID'

  def owner_payout_status(self, obj):
    if obj.batch_status:
      return obj.batch_status
    return 'Unsent'

  owner_payout_status.short_description = 'Payout status'

  def owner_payout_fee(self, obj):
    if obj.paypal_fee:
      return obj.paypal_fee
    return 'None yet'

  owner_payout_fee.short_description = 'Owner fee'

  def who_to_pay_email(self, obj):
    return obj.who_to_pay.email

  who_to_pay_email.short_description = 'Who to pay'


admin.site.register(OwnerPayout, OwnerPayoutAdmin)
