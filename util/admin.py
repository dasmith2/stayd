from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, reverse, redirect

from util.urls import date_to_url_str, dates_from_strs, date_to_date_picker_str


def admin_context(title, **kwargs):
  kwargs = kwargs or {}
  kwargs.update({
      'title': title,
      'site_title': title,
      'site_header': 'Stayd administration'})
  return kwargs


@staff_member_required
def simple_date_range_admin_page(
    request,
    from_date_str, to_date_str, default_from, default_to,
    view_name, title, template,
    context_stuff_func):
  if not from_date_str and not to_date_str:
    return redirect(reverse(view_name, kwargs={
        'from_date_str': date_to_url_str(default_from),
        'to_date_str': date_to_url_str(default_to)}))

  from_date, to_date = dates_from_strs(from_date_str, to_date_str)

  context = admin_context(
      title,
      from_date_str=date_to_date_picker_str(from_date),
      to_date_str=date_to_date_picker_str(to_date))
  context.update(context_stuff_func(from_date, to_date))
  return render(request, template, context=context)
