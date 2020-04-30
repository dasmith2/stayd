from django.contrib import admin

from util.admin import ModelAdmin
from xxero.models import Transaction
from xxero.models.businesses import Business


@admin.register(Transaction)
class TransactionAdmin(ModelAdmin):
  list_display = (
      'when', 'bank_account', 'xero_type', 'amount', 'contact',
      'transfer_bank')


@admin.register(Business)
class BusinessAdmin(ModelAdmin):
  list_display = ('name',)
