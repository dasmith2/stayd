from django.contrib import admin
from pays.models import PaypalPayout


class PaypalPayoutAdmin(admin.ModelAdmin):
  list_display = ['email', 'amount', 'fee', 'when', 'batch_status']
  ordering = ['when']


admin.site.register(PaypalPayout, PaypalPayoutAdmin)
