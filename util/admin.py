import re

from django.contrib import admin
from django.http import HttpResponseBadRequest
from django.shortcuts import render, reverse, redirect
from django.urls.exceptions import NoReverseMatch

from util.urls import (
    date_to_url_str, dates_from_strs, date_to_date_picker_str,
    data_to_query_string)


class ModelAdmin(admin.ModelAdmin):
  class Media:
    js = (
        '//code.jquery.com/jquery-1.12.4.js',
        'admin_helptext_hack.js')


def admin_context(title, **kwargs):
  use_kwargs = {'title': title, 'site_title': title}
  use_kwargs.update(kwargs)
  return use_kwargs


def dated_admin_context(
    title, from_date, to_date, date_error, request, **kwargs):
  """ Do, like,
  def my_page(request, from_date_str, to_date_str):
    from_date, to_date, date_error = dates_from_strs(
        from_date_str, to_date_str)
    context = dated_admin_context(
        'My page', from_date, to_date, date_error, request, foo='bar')
    if not date_error:
      context['whatever'] = stuff(from_date, to_date)
    return render(request, 'my_page.html', context=context)
  """
  return admin_context(
      title,
      from_date_str=date_to_date_picker_str(from_date),
      to_date_str=date_to_date_picker_str(to_date),
      error=date_error,
      **kwargs)


def simple_table_page(
    request, view_name_or_url, title, template='simple_table.html', error=None,
    table=None, **kwargs):
  if request.GET.get('csv', None) == 'true' and table:
    file_name = re.compile(r'[^\w]').sub('', view_name_or_url) + '.csv'
    return table.csv_response(file_name)

  try:
    generate_csv_url = reverse(view_name_or_url)
  except NoReverseMatch:
    generate_csv_url = view_name_or_url
  context = admin_context(
      title, error=error, table=table, generate_csv_url=generate_csv_url,
      **kwargs)
  return render(request, template, context=context)


def simple_date_range_admin_page(
    request, from_date_str, to_date_str, default_from, default_to,
    view_name, title, template='dated_report.html',
    context_stuff_func=None, table=None, generate_csv_kwargs=None, **kwargs):
  """ This function is amazing! It lets you easily turn a date range util.Table
  into an admin page. It comes with date filters and a download csv button for
  free. pay_service_provider_totals in properly.views is a great example. """
  if not from_date_str and not to_date_str:
    query_string = data_to_query_string(request.GET)
    return redirect(reverse(view_name, kwargs={
        'from_date_str': date_to_url_str(default_from),
        'to_date_str': date_to_url_str(default_to)}) + query_string)
  if request.GET.get('csv', None) == 'true' and table:
    return table.csv_response(view_name + '.csv')

  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  if error:
    return HttpResponseBadRequest('I was unable to parse the dates in the url')

  generate_csv_url = reverse(view_name, kwargs={
      'from_date_str': from_date_str, 'to_date_str': to_date_str})

  context = admin_context(
      title,
      from_date_str=date_to_date_picker_str(from_date) or from_date_str,
      to_date_str=date_to_date_picker_str(to_date) or to_date_str,
      error=error, table=table, generate_csv_url=generate_csv_url,
      generate_csv_kwargs=generate_csv_kwargs or {}, **kwargs)
  if context_stuff_func:
    context.update(context_stuff_func(from_date, to_date))
  return render(request, template, context=context)


def simple_resolution_page(
    request, title, resolution_form, template='simple_resolution.html',
    breadcrumb_url=None, breadcrumb_title=None, **kwargs):
  context = admin_context(
      title, resolution_form=resolution_form,
      breadcrumb_url=breadcrumb_url,
      breadcrumb_title='Unresolved: Likely payin != ideal payin', **kwargs)
  return render(request, template, context)
