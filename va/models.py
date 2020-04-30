from django.db import models
from django.shortcuts import reverse

from guest_messages.models.email import (
    Email, checkin_instructions_template)
from util.background import background
from util.table import Table, Cell
from util.timezone import tz_dt_to_str


class Announcement(models.Model):
  """ Classic content management here. Every announcement has a start time and
  an end time. During that span, show the announcement at the top of the VA
  pages. """
  text = models.TextField(help_text=(
      'What would you like to say to the VAs? HTML is allowed.'))
  start = models.DateTimeField(help_text=(
      'When would you like this message to appear at the top of the VA '
      'pages?'))
  end = models.DateTimeField(help_text=(
      'When would you like this message to no longer appear?'))


def risk_css(reservation):
  if reservation.riskscore_or_none:
    if reservation.riskscore.high_risk():
      return 'high_risk'
    elif reservation.riskscore.medium_risk():
      return 'medium_risk'


def reservations_table(reservations, reservation_view):
  table = Table([
      'Channel ID', 'Guest', 'Check in', 'Check out', 'Rental'])
  for reservation in reservations:
    classes = []
    css = risk_css(reservation)
    if css:
      classes = [css]

    url = reverse(reservation_view, kwargs={'pk': reservation.pk})
    table.create_row([
        Cell(reservation.channel_id, url=url),
        reservation.guest.get_name(), reservation.get_check_in(),
        reservation.get_check_out(),
        reservation.rental.nickname], classes=classes)
  return table


def handle_checkin_instructions(reservation, post, is_superuser, emailer=None):
  """ Handle the post and return context related to sending checkin
  instructions. """
  # What's happened so far
  sent_email = None
  unsent_email = None
  for email in Email.objects.get_checkin_instructions(reservation):
    if email.when_did:
      sent_email = email
    else:
      unsent_email = email

  # Explain things
  why_not_auto_send_checkin_instructions = None
  why_cant_manually_send_checkin_instructions = None
  email_template = checkin_instructions_template()
  send_checkin_instructions_problem = None
  if not email_template:
    why_not_auto_send_checkin_instructions = (
        'there is no checkin instructions email template')
    why_cant_manually_send_checkin_instructions = (
        why_not_auto_send_checkin_instructions)
  if unsent_email:
    if unsent_email.about_to_send:
      why_cant_manually_send_checkin_instructions = (
          'I\'m trying to send them as we speak')
    else:
      why_not_auto_send_checkin_instructions = (
          unsent_email.explain_why_do_not_send())
  if why_not_auto_send_checkin_instructions and not is_superuser:
    why_cant_manually_send_checkin_instructions = (
        why_cant_manually_send_checkin_instructions or (
            why_not_auto_send_checkin_instructions))

  # Possibly do things
  if post and 'manually_send_checkin_instructions' in post:
    if why_cant_manually_send_checkin_instructions:
      send_checkin_instructions_problem = (
          'I didn\'t just send the checkin instructions because {}').format(
              why_cant_manually_send_checkin_instructions)
    else:
      if not unsent_email:
        unsent_email = email_template.create_new_message(reservation)
      unsent_email.about_to_send = True
      manual_email = post.get('manual_email', None)
      if manual_email:
        unsent_email.send_to_override = manual_email
      unsent_email.save()
      send_checkin_instructions(unsent_email.pk, emailer=emailer)
      why_cant_manually_send_checkin_instructions = (
          'I\'m trying to send them as we speak')

  # Now what's happening?
  checkin_instructions_sent = 'Never sent.'
  if unsent_email:
    if unsent_email.about_to_send:
      checkin_instructions_sent = 'Sending...'
    else:
      checkin_instructions_sent = 'Unsent. Scheduled for {} (NYC time)'.format(
          tz_dt_to_str(unsent_email.when_should))
  elif sent_email:
    checkin_instructions_sent = 'Sent {} (NYC time)'.format(
        tz_dt_to_str(sent_email.when_did))

  why_not_auto = why_not_auto_send_checkin_instructions
  return {
      'submit_id_url': reservation.verify_id_url(),
      'checkin_instructions_sent': checkin_instructions_sent,
      'why_not_auto_send_checkin_instructions': why_not_auto,
      'id_not_verified': not reservation.id_verified,
      'send_checkin_instructions_problem': send_checkin_instructions_problem,
      'why_cant_manually_send_checkin_instructions': (
          why_cant_manually_send_checkin_instructions)}


@background
def send_checkin_instructions(email_pk, emailer=None):
  Email.objects.send(message_pk=email_pk, emailer=emailer)


def reservation_meta_table(reservation, is_superuser):
  headers = [
      'Guesty', 'Channel', 'Guest', 'Booked on', 'Check in', 'Check out',
      'Rental', 'Phone', 'Status']
  cells = [
      Cell(reservation.channel_id, url=reservation.admin_url()),
      reservation.channel,
      reservation.guest.full_name,
      reservation.get_booked_at(), reservation.get_check_in(),
      reservation.get_check_out(), reservation.rental.nickname,
      reservation.guest.phone, reservation.status]
  if is_superuser:
    headers.append('Last synced')
    cells.append(reservation.last_synced_at)
  res_table = Table(headers)
  res_table.create_row(cells)
  return res_table
