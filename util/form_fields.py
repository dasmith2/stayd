"""
Now you can do, like,
class BlarghForm(forms.Form):
  day = form_fields.DateField()

and it'll render as <input type="date" ...> which is the easiest way to do a
client side date picker I know of.
"""
from django import forms

from util import widgets


class DateField(forms.DateField):
  widget = widgets.DateInput


class TimeField(forms.TimeField):
  widget = widgets.TimeInput
