from datetime import date

from django.shortcuts import reverse

from reservations.models import Reservation, CONFIRMED
from util.table import Table, Cell


def dashboard_table_reservations(from_date, to_date):
  return Reservation.objects.filter(
      rental__building__background_check_guests=True,
      check_in__date__gte=from_date, check_in__date__lt=to_date).order_by(
          '-check_in')


def dashboard_totals(reservations):
  status_provider_counts = {}
  total = 0
  for reservation in reservations:
    total += 1
    if reservation.backgroundcheck_or_none:
      bgcheck = reservation.backgroundcheck
      provider = bgcheck.provider
      status = bgcheck.status()
      key = '{} {}'.format(status, provider)
      if key not in status_provider_counts:
        status_provider_counts[key] = 0
      status_provider_counts[key] += 1

  columns = ['Total']
  cells = [total]
  for (key, value) in status_provider_counts.items():
    columns.append(key)
    cells.append(value)

  table = Table(columns)
  table.create_row(cells)
  return table


def dashboard_table(reservations):
  today = date.today()
  table = Table([
      'Check in', 'Check out', 'BGCheck', 'Completed at', 'Provider',
      'Breach?', 'Guest', 'Rental', 'Admin', 'Keys', 'Res status'])
  for reservation in reservations:
    rental = reservation.rental.nickname
    guest = reservation.guest.full_name
    admin = Cell(reservation.channel_id, url=reservation.admin_url())
    keys = Cell(reservation.pk, url=reservation.keys_url())
    res_status = reservation.status
    check_in = reservation.check_in.date()
    check_out = reservation.check_out.date()
    bgcheck = None
    provider = None
    passed = False
    if reservation.backgroundcheck_or_none:
      bgcheck = reservation.backgroundcheck
      passed = bgcheck.passed
      provider = bgcheck.provider
    bgcheck_cell_text = bgcheck.status() if bgcheck else 'No bgcheck'
    completed_at = bgcheck.completed_at if bgcheck else None
    bgcheck_cell = Cell(bgcheck_cell_text, url=reverse(
        'bgcheck_detail', kwargs={'reservation_pk': reservation.pk}))
    breach = None
    if reservation.status == CONFIRMED and not passed and (
        today >= reservation.check_in.date() and (
            today <= reservation.check_out.date())):
      breach = Cell('Breach!', classes=['alert'])
    table.create_row([
        check_in, check_out, bgcheck_cell, completed_at, provider, breach,
        guest, rental, admin, keys, res_status])
  return table


def detail(reservation):
  table = Table(['Key', 'Value'])
  rows = [
      ['Rental', reservation.rental.nickname],
      ['Guest', reservation.guest.full_name],
      ['Admin', reservation.admin_url()],
      ['Keys', reservation.keys_url()],
      ['Res_status', reservation.status],
      ['Check_in', reservation.check_in.date()],
      ['Check_out', reservation.check_out.date()]]
  if not reservation.backgroundcheck_or_none:
    rows.append(['BGCheck', None])
  else:
    bgcheck = reservation.backgroundcheck
    rows.extend([
        ['BGCheck pk', bgcheck.pk],
        ['BGCheck provider', bgcheck.provider],
        ['BGCheck passed', bgcheck.passed],
        ['BGCheck created_at', bgcheck.created_at],
        ['BGCheck got_valid_submission_at', bgcheck.got_valid_submission_at],
        ['BGCheck completed_at', bgcheck.completed_at],
        ['BGCheck not_completed_in_time', bgcheck.not_completed_in_time]])

    if not bgcheck.submission:
      rows.append(['Submission', None])
    else:
      submission = bgcheck.submission
      pssa = submission.post_submission_steps_at
      rows.extend([
          ['Submission pk', submission.pk],
          ['Submission created_at', submission.created_at],
          ['Submission birthday', submission.birthday],
          ['Submission legal_name', submission.legal_name],
          ['Submission id_type', submission.id_type],
          ['Submission opt_out_of_bgcheck', submission.opt_out_of_bgcheck],
          ['Submission checked_at', submission.checked_at],
          ['Submission checked_by', submission.checked_by],
          ['Submission risk_score', submission.risk_score],
          ['Submission post_submission_steps_at', pssa]])
    for chemail in bgcheck.reservation.chemail_set.all():
      rows.extend([
          ['Guest notification when', chemail.when],
          ['Guest notification to', chemail.to]])

  for row in rows:
    table.create_row(row)
  return table
