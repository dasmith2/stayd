from django import forms

from rentals.models import Rental


class AdjustmentForm(forms.Form):
  def __init__(self, owner_payout, *args, **kwargs):
    super(AdjustmentForm, self).__init__(*args, **kwargs)

    owner = owner_payout.owner()
    choices = []
    for rental in Rental.objects.filter(owner=owner):
      choices.append((rental.pk, rental.airbnb_address_scrape))

    self.fields['rental'].choices = choices

  rental = forms.ChoiceField(label='Rental')
  amount = forms.DecimalField(label='Amount', help_text=(
      'This is usually negative.'))
  reason = forms.CharField(label='Reason', widget=forms.Textarea)
