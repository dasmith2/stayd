from django.contrib import admin
from pays.models import PaypalPayout


class PaypalPayoutAdmin(admin.ModelAdmin):
  list_display = [
      'paypal_payout_id', 'who_to_pay_email', 'amount', 'green_light',
      'when_should', 'when_did', 'paypal_payout_status', 'paypal_payout_fee']
  ordering = ['when_should']

  def paypal_payout_id(self, obj):
    return obj.public_id

  paypal_payout_id.short_description = 'ID'

  def paypal_payout_status(self, obj):
    if obj.batch_status:
      return obj.batch_status
    return 'Unsent'

  paypal_payout_status.short_description = 'Payout status'

  def paypal_payout_fee(self, obj):
    if obj.paypal_fee:
      return obj.paypal_fee
    return 'None yet'

  paypal_payout_fee.short_description = 'Paypal fee'

  def who_to_pay_email(self, obj):
    return obj.who_to_pay.email

  who_to_pay_email.short_description = 'Who to pay'


admin.site.register(PaypalPayout, PaypalPayoutAdmin)
