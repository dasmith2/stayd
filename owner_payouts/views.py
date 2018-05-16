from django.shortcuts import render
from djmoney.money import Money

from owner_payouts.forms import AdjustmentForm
from owner_payouts.models import OwnerPayout, Adjustment
from rentals.models import Rental
from util.fake_admin import admin_context


def edit_owner_payout(request, owner_payout_id):
  owner_payout = OwnerPayout.objects.get(pk=owner_payout_id)
  adjustment_form = AdjustmentForm(owner_payout)
  if request.method == 'POST' and not owner_payout.is_sent():
    delete_id = request.POST.get('delete_adjustment', '')
    if request.POST.get('block', ''):
      owner_payout.green_light = False
      owner_payout.save()
    elif request.POST.get('enable', ''):
      owner_payout.green_light = True
      owner_payout.save()
    elif delete_id:
      Adjustment.objects.get(pk=int(delete_id)).delete()
    elif request.POST.get('create', ''):
      adjustment_form = AdjustmentForm(owner_payout, request.POST)
      if adjustment_form.is_valid():
        amount = Money(adjustment_form.cleaned_data['amount'], 'USD')
        reason = adjustment_form.cleaned_data['reason']
        rental = Rental.objects.get(pk=adjustment_form.cleaned_data['rental'])
        Adjustment.objects.create(
            payout=owner_payout,
            amount=amount,
            reason=reason,
            rental=rental)
        owner_payout.calculate_amount_and_save()
        adjustment_form = AdjustmentForm(owner_payout)

  context = admin_context(
      'Owner payout details',
      owner_payout=owner_payout,
      adjustment_form=adjustment_form)
  return render(request, 'admin/owner_payout.html', context=context)
