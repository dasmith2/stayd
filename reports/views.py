from datetime import datetime, timedelta, date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse

from reports.models import get_rent_revenues
from util.fake_admin import admin_context


DATE_FORMAT = '%m-%d-%Y'


@login_required
def rent_revenue(request, from_date_str='', to_date_str=''):
  """ The datepicker does 05/21/2018, but slashes and urls, so the js turns it
  to dashes first. So these date strings are coming in like 05-21-2018.
  Turn it back to slashes before it goes back out in the context so the
  template can speak the language of the picker. """
  if not from_date_str and not to_date_str:
    return redirect(reverse('rent_revenue', kwargs={
        'from_date_str': date_to_str(date.today()),
        'to_date_str': date_to_str(date.today() + timedelta(days=30))}))

  context = admin_context(
      'Revenue and market rent',
      from_date_str=from_date_str.replace('-', '/'),
      to_date_str=to_date_str.replace('-', '/'))

  if from_date_str and to_date_str:
    from_date = date_from_str(from_date_str)
    # OK, big fudge here. I feel like, for programmers it makes sense to
    # have an exclusive to_date, meaning that if you want to query about
    # February you do 2/1/2018 through 3/1/2018. But I think in the user
    # interface you'd expect to query 2/1/2018 through 2/28/2018.
    # So I add a day here.
    to_date = date_from_str(to_date_str) + timedelta(days=1)
    context['rent_revenues'] = get_rent_revenues(from_date, to_date)

  return render(request, 'reports/rent_revenue.html', context=context)


def date_to_str(dte):
  return dte.strftime(DATE_FORMAT)


def date_from_str(date_str):
  return datetime.strptime(date_str, DATE_FORMAT).date()
