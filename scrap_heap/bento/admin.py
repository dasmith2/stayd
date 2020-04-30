from django.contrib import admin

from bento.models import Card, Transaction, Tag
from util.admin import ModelAdmin


@admin.register(Card)
class CardAdmin(ModelAdmin):
  list_display = ('alias', 'building')
  list_editable = ('building',)


@admin.register(Tag)
class TagAdmin(ModelAdmin):
  list_display = ('name', 'building')
  list_editable = ('building',)


@admin.register(Transaction)
class TransactionAdmin(ModelAdmin):
  def card_alias(self, instance):
    if instance.card:
      return instance.card.alias

  def complete(self, instance):
    return instance.status == 'COMPLETE'
  complete.boolean = True

  list_display = (
      'card_alias', 'amount', 'transaction_date', 'payee', 'building',
      'complete')
  list_editable = ('building',)
  list_select_related = ('card', 'building')
