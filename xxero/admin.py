from django.contrib import admin

from xxero.models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
  list_display = (
      'when', 'bank_account', 'xero_type', 'amount', 'contact',
      'transfer_bank')
