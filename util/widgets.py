""" When you do, like,
class BlarghForm(forms.Form):
  day = forms.DateField()

Django renders that as <input type="text" ...> which isn't very helpful. But
html has all kinds of rad input types available now. They may not necessarily
be pretty, but the work and they're easy to use. So now you can do

  day = forms.DateField(widget=widgets.DateInput)

which will render as <input type="date" ...>

But actually you probably just want to use util/form_fields.py
"""
from django.forms.widgets import DateTimeBaseInput


class DateInput(DateTimeBaseInput):
  """ This is pretty much an exact copy of django.forms.widgets.DateInput with
  one very crucial difference. """
  input_type = 'date'  # The only clever thing I added.
  format_key = 'DATE_INPUT_FORMATS'
  template_name = 'django/forms/widgets/date.html'


class TimeInput(DateTimeBaseInput):
  input_type = 'time'  # The only clever thing I added.
  format_key = 'TIME_INPUT_FORMATS'
  template_name = 'django/forms/widgets/time.html'
