# flake8: noqa
from reports.cash_basis.cash_basis import get_cash_basis_table
from xxero.models.coconuts import Coconut


@login_required
@can_groups(ACCOUNTANT)
def cash_basis(request, from_date_str='', to_date_str=''):
  if not from_date_str and not to_date_str:
    return redirect(reverse('cash_basis', kwargs={
        'from_date_str': date_to_url_str(date.today() - timedelta(days=30)),
        'to_date_str': date_to_url_str(date.today())}))
  from_date, to_date, date_error = dates_from_strs(from_date_str, to_date_str)
  context = dated_admin_context(
      'Cash basis', from_date, to_date, date_error, request)
  if not date_error:
    context['cash_basis_table'] = get_cash_basis_table(from_date, to_date)
    generate_csv_url = reverse(
        'cash_basis_csv', kwargs={
            'from_date_str': from_date_str, 'to_date_str': to_date_str})
    context['generate_csv_url'] = generate_csv_url
  return render(request, 'cash_basis/cash_basis.html', context=context)


@login_required
@can_groups(ACCOUNTANT)
def cash_basis_csv(request, from_date_str, to_date_str):
  from_date, to_date, date_error = dates_from_strs(from_date_str, to_date_str)
  if date_error:
    return HttpResponseBadRequest('I was unable to parse the dates in the url')
  return get_cash_basis_table(
      from_date, to_date).csv_response('cash_basis.csv')


@login_required
@can_groups(ACCOUNTANT)
def coconut_details(
    request, from_date_str, to_date_str, coconut_id, building_id):
  from_date, to_date, date_error = dates_from_strs(from_date_str, to_date_str)
  generate_csv_url = reverse(
      'coconut_details_csv', kwargs={
          'from_date_str': from_date_str, 'to_date_str': to_date_str,
          'coconut_id': coconut_id, 'building_id': building_id})
  coconut = Coconut.objects.get(pk=coconut_id)
  building = Building.objects.get(pk=building_id)
  title = '{} {}'.format(coconut.name, building.nickname)
  context = dated_admin_context(
      title, from_date, to_date, date_error, request,
      generate_csv_url=generate_csv_url,
      breadcrumb_url=_breadcrumb_url(from_date_str, to_date_str))
  if not date_error:
    context['building_coconut_transactions_table'] = (
        get_building_coconut_transactions_table(
            from_date, to_date, coconut_id, building_id))
  return render(request, 'cash_basis/coconut_details.html', context=context)


@login_required
@can_groups(ACCOUNTANT)
def coconut_details_csv(
    request, from_date_str, to_date_str, coconut_id, building_id):
  from_date, to_date, date_error = dates_from_strs(from_date_str, to_date_str)
  if date_error:
    return HttpResponseBadRequest('I was unable to parse the dates in the url')
  return get_building_coconut_transactions_table(
      from_date, to_date, coconut_id, building_id).csv_response(
          'cash_basis_coconut.csv')
