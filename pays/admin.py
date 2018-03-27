from django.contrib import admin
from pays.models import PaypalPayout


class PaypalPayoutAdmin(admin.ModelAdmin):
  list_display = [
      'email', 'amount', 'on_hold', 'fee', 'when_should', 'when_did',
      'batch_status']
  ordering = ['when_should']


admin.site.register(PaypalPayout, PaypalPayoutAdmin)
