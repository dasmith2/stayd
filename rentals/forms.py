from django import forms
from django.core.exceptions import ValidationError

from rentals.models import Rental, Building


class RentalForm(forms.ModelForm):
  class Meta:
    fields = (
        'building', 'apartment', 'reports_start_date', 'reports_end_date',
        'is_combo_of', 'maintenance_purposes_only')
    model = Rental

  def clean(self, *args, **kwargs):
    is_combo_of = self.cleaned_data.get('is_combo_of', [])
    if is_combo_of and self.instance.pk:
      parent = Rental.objects.filter(is_combo_of=self.instance).first()
      if parent:
        message = (
            'This rental, {}, can\'t be a combo rental because it\'s in {}\'s '
            'combo.').format(self.instance.nickname, parent.nickname)
        raise ValidationError(message)
    for combo_of in is_combo_of:
      if combo_of.is_combo_rental():
        message = (
            '{} is itself a combo rental and therefore can\'t be in this '
            'rental\'s is_combo_of list.').format(combo_of.nickname)
        raise ValidationError(message)
    return super().clean(*args, **kwargs)


class BuildingForm(forms.ModelForm):
  class Meta:
    fields = (
        'owner', 'nickname', 'is_active', 'alerts_email', 'sms_staff_from',
        'background_check_guests')
    model = Building
