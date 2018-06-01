from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from reports.models import get_rent_revenues
from util.fake_admin import admin_context


@login_required
def rent_revenue(request, from_date_str='', to_date_str=''):
  """ The datepicker does 05/21/2018, but slashes and urls, so the js turns it
  to dashes first. So these date strings are coming in like 05-21-2018.
  Turn it back to slashes before it goes back out in the context so the
  template can speak the language of the picker. """
  context = admin_context(
      'Rent and revenue',
      from_date_str=from_date_str.replace('-', '/'),
      to_date_str=to_date_str.replace('-', '/'))
  if from_date_str and to_date_str:
    from_date = date_from_str(from_date_str)
    to_date = date_from_str(to_date_str)
    rent_revenues = get_rent_revenues(from_date, to_date)
    context['total'] = rent_revenues.total
    context['cities'] = rent_revenues.cities
    context['rentals'] = rent_revenues.rentals

  return render(request, 'reports/rent_revenue.html', context=context)


def date_from_str(date_str):
  return datetime.strptime(date_str, '%m-%d-%Y').date()
