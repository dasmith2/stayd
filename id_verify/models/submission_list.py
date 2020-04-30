from id_verify.models import Submission
from util.table import Table, Cell


def get_submission_list_table(reservation, is_superuser):
  bgcheck = reservation.rental.building.background_check_guests
  headers = ['Valid?', 'Email', 'Phone', 'Submitted', 'ID matches reservation']
  if reservation.we_assume_cc_risk():
    headers.extend(['ID matches cc', 'CC matches reservation'])
  headers.extend([
      'Checked at', 'Checked by', 'Risk score', 'If not checked, why?'])
  if is_superuser:
    headers.append('ID photo')
    if bgcheck:
      headers.append('ID back')
    if reservation.we_assume_cc_risk():
      headers.append('CC photo')
  table = Table(headers)
  for submission in Submission.objects.filter(
      reservation=reservation).order_by('created_at'):
    checked_by = None
    if submission.checked_by:
      checked_by = '{} {}'.format(
          submission.checked_by.username, submission.checked_by.email)
    why_not_checked = None
    if not submission.checked_at:
      why_not_checked = submission.explain_why_not_check()
    cells = [
        submission.all_good(), submission.email, submission.phone,
        submission.created_at, submission.id_matches_res]
    if reservation.we_assume_cc_risk():
      cells.extend([submission.cc_matches_id, submission.cc_matches_payment])
    cells.extend([
        submission.checked_at, checked_by, submission.risk_score,
        why_not_checked])
    if is_superuser:
      cells.append(_photo_cell(submission.id_photo()))
      if bgcheck:
        cells.append(_photo_cell(submission.id_back_photo()))
      if reservation.we_assume_cc_risk():
        cells.append(_photo_cell(submission.cc_photo()))
    table.create_row(cells)
  return table


def _photo_cell(photo):
  if photo:
    if photo.resized_at:
      return Cell(photo.photo_type, url=photo.url())
    elif not photo.valid:
      return 'This isn\'t a valid image file'
    return 'Resizing...'
