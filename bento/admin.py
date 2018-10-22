from django.contrib import admin

from bento.models import Card, Transaction, TagToBuilding


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
  list_display = ('alias', 'building')
  list_editable = ('building',)


@admin.register(TagToBuilding)
class TagToBuildingAdmin(admin.ModelAdmin):
  list_display = ('tag', 'building')
  list_editable = ('building',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
  def card_alias(self, instance):
    if instance.card:
      return instance.card.alias

  def complete(self, instance):
    return instance.status == 'COMPLETE'
  complete.boolean = True

  list_display = (
      'card_alias', 'amount', 'transaction_date', 'payee', 'tag', 'building',
      'complete')
  list_editable = ('building',)
