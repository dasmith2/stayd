from django.contrib import admin

from stripe.models import Payout, BalanceTransaction, Fee, Charge, Refund
from util.admin import ModelAdmin


@admin.register(Payout)
class PayoutAdmin(ModelAdmin):
  list_display = ('payout_id', 'amount', 'arrival_date')


@admin.register(BalanceTransaction)
class BalanceTransactionAdmin(ModelAdmin):
  list_display = (
      'balance_transaction_id', 'payout', 'amount', 'total_fees', 'net',
      'currency', 'ttype', 'status')


@admin.register(Fee)
class FeeAdmin(ModelAdmin):
  list_display = ('balance_transaction', 'description', 'amount')


@admin.register(Charge)
class ChargeAdmin(ModelAdmin):
  list_display = (
      'charge_id', 'balance_transaction', 'amount', 'refunds_synced_at',
      'amount_refunded', 'created', 'cc_last_4', 'cc_brand', 'dispute_id')


@admin.register(Refund)
class RefundAdmin(ModelAdmin):
  list_display = ('refund_id', 'charge', 'balance_transaction', 'amount')
