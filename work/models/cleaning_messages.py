""" Messages that apply specifically to cleanings.

Vision: all notifications less than 24 hours are timely interruptions. Keep
those. There's also a daily email and a keys dashboard that includes everything
up to 48 hours. """
from datetime import timedelta

from django.shortcuts import reverse

from commands.models import background_command
from errors.models import log_error
from work.models.cleaning import Cleaning
from work.models.message import (
    Message, SubjectLine, MessageSender, UNCLAIMED_CLEANING_IN_LT_48_HOURS,
    UNCLAIMED_CLEANING_IN_LT_24_HOURS, UNCLAIMED_CLEANING_IN_LT_4_HOURS,
    CLEANING_TAKING_TOO_LONG, CLEANING_NOT_FINISHED_CHECK_IN_IN_25_MINUTES,
    EMAIL,
    CLEAN_CO_CLEANING_NOT_DONE_BY_3_00,
    CLEAN_CO_CLEANING_NOT_DONE_BY_3_10,
    CLEAN_CO_CLEANING_NOT_ASSIGNED_2_HOURS_BEFORE,
    CLEAN_CO_CLEANING_NOT_ASSIGNED_3_HOURS_BEFORE,
    CLEAN_CO_CLEANING_NOT_ASSIGNED_18_HOURS_BEFORE,
    CLEAN_CO_CLEANING_NOT_ASSIGNED_24_HOURS_BEFORE,
    NEW_CLEANING_AVAILABLE, CONFIRMED_NO_CLEANING)
from util.timezone import now, tz_dt_to_tz_dt, tz_dt_to_str


@background_command
def send_through_the_day_cleaning_messages_background():
  """ I used to be more thoughtful about these, lovingly scheduling each one.
  But then there were kind of a lot of messages and then we were in a bunch of
  timezones and it started to get unruly. So now I just run these every 5
  minutes basically from 10am new york time to 6pm arizona time. """
  send_unclaimed_cleaning_in_lt_x_hours(
      start_within_hours=48, reason=UNCLAIMED_CLEANING_IN_LT_48_HOURS)
  send_unclaimed_cleaning_in_lt_x_hours(
      start_within_hours=24, reason=UNCLAIMED_CLEANING_IN_LT_24_HOURS)
  send_unclaimed_cleaning_in_lt_x_hours(
      start_within_hours=4, reason=UNCLAIMED_CLEANING_IN_LT_4_HOURS)
  send_independent_cleaning_taking_too_long_notifications()
  send_check_in_soon_notifications()
  send_cleaning_unasigned()
  send_work_co_not_finished_by_3ish()
  send_confirmed_no_cleaning()


def send_confirmed_no_cleaning(nnow=None, message_sender=None):
  nnow = nnow or now()
  message_sender = message_sender or MessageSender()
  for cleanable in Cleaning.objects.confirmed_no_cleaning(nnow=nnow):
    subject = 'Cleaning blocked at {} on {}'.format(
        cleanable.rental.nickname, cleanable.get_start_time().date())
    explanation = Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
        cleanable.reservation)
    if explanation:
      message = (
          '{}\n{}\n{}\n\nKeys won\'t create this cleaning because {}. '
          'Usually, this is correct and you don\'t have to do anything. '
          'But sometimes the reservation has been mishandled somehow and this '
          'cleaning really does need to happen. If that\'s the case, '
          'manually create a One Off.').format(
              cleanable.reservation.guest.full_name,
              cleanable.reservation.keys_url(),
              cleanable.reservation.admin_url(),
              explanation)
    else:
      log_error('Keys SHOULD have created this cleaning already', (
          '{}\n\nThere\'s nothing blocking this cleaning, yet it doesn\'t '
          'exist yet. As soon as all the factors blocking the cleaning '
          'were removed, it should have created a '
          'cleaning.').format(cleanable.reservation.keys_url()))
    if not Message.objects.filter(
        reason=CONFIRMED_NO_CLEANING, subject=subject,
        when__gte=nnow - timedelta(hours=12)).exists():
      message_sender.send(Message.objects.create(
          to=cleanable.rental.building.alerts_email,
          reason=CONFIRMED_NO_CLEANING, kind=EMAIL, subject=subject,
          content=message, work=None, when=nnow))


def send_new_cleaning_available(nnow=None, message_sender=None):
  nnow = nnow or now()
  message_sender = message_sender or MessageSender()
  for cleaning in Cleaning.objects.filter(
      created_at__gte=nnow - timedelta(days=1),
      rental__properlyrental__clean_co__isnull=False):
    if not Message.objects.filter(
        work=cleaning, reason=NEW_CLEANING_AVAILABLE).exists():
      subject = SubjectLine.objects.get_subject_line(NEW_CLEANING_AVAILABLE)
      url = 'https://clean.hihoward.com{}'.format(
          reverse('clean_co_cleanings'))
      message_sender.send(Message.objects.create(
          to=cleaning.get_work_co().alerts_email,
          reason=NEW_CLEANING_AVAILABLE, kind=EMAIL, subject=subject,
          content=url, work=cleaning, when=nnow))


def send_cleaning_unasigned(nnow=None, message_sender=None):
  nnow = nnow or now()
  message_sender = message_sender or MessageSender()
  for cleaning in Cleaning.objects.filter(
      offered_to__isnull=True, offered_start_time__gte=nnow,
      offered_start_time__lte=nnow + timedelta(hours=24),
      canceled_at__isnull=True).select_related(
          'rental', 'rental__building', 'reservation'):
    if cleaning.uses_work_co():
      time_until_cleaning = cleaning.offered_start_time - nnow
      work_co = cleaning.get_work_co()
      reason_24 = CLEAN_CO_CLEANING_NOT_ASSIGNED_24_HOURS_BEFORE
      reason_18 = CLEAN_CO_CLEANING_NOT_ASSIGNED_18_HOURS_BEFORE
      reason_3 = CLEAN_CO_CLEANING_NOT_ASSIGNED_3_HOURS_BEFORE
      reason_2 = CLEAN_CO_CLEANING_NOT_ASSIGNED_2_HOURS_BEFORE
      if not Message.objects.filter(work=cleaning, reason=reason_24).exists():
        content = (
            'Hello! There is a cleaning at {} in 24 hours with nobody '
            'assigned to it.').format(cleaning.get_rental().nickname)
        message_sender.send(Message.objects.create(
            to=work_co.alerts_email, reason=reason_24, kind=EMAIL,
            subject=reason_24, content=content, work=cleaning, when=nnow))
      elif time_until_cleaning <= timedelta(hours=18) and not (
          Message.objects.filter(work=cleaning, reason=reason_18).exists()):
        message_sender.send(Message.objects.create(
            to=cleaning.alerts_email(), reason=reason_18,
            kind=EMAIL, subject=reason_18,
            content=_simple_work_co_alert_content(cleaning), work=cleaning,
            when=nnow))
      elif time_until_cleaning <= timedelta(hours=3) and not (
          Message.objects.filter(work=cleaning, reason=reason_3).exists()):
        content = (
            'Hello! There is a cleaning at {} in 3 hours with nobody '
            'assigned to it.').format(cleaning.get_rental().nickname)
        message_sender.send(Message.objects.create(
            to=work_co.alerts_email, reason=reason_3, kind=EMAIL,
            subject=reason_3, content=content, work=cleaning, when=nnow))
      elif time_until_cleaning <= timedelta(hours=2) and not (
          Message.objects.filter(work=cleaning, reason=reason_2).exists()):
        message_sender.send(Message.objects.create(
            to=cleaning.alerts_email(), reason=reason_2,
            kind=EMAIL, subject=reason_2,
            content=_simple_work_co_alert_content(cleaning), work=cleaning,
            when=nnow))


def send_work_co_not_finished_by_3ish(nnow=None, message_sender=None):
  nnow = nnow or now()
  message_sender = message_sender or MessageSender()
  for cleaning in Cleaning.objects.filter(
      completed_at__isnull=True,
      offered_start_time__gte=nnow - timedelta(days=1)):
    if cleaning.uses_work_co():
      building = cleaning.get_rental().building
      their_time_3 = tz_dt_to_tz_dt(
          cleaning.offered_start_time, building.time_zone).replace(
              hour=15, minute=0, second=0, microsecond=0)
      their_time_3_10 = tz_dt_to_tz_dt(
          cleaning.offered_start_time, building.time_zone).replace(
              hour=15, minute=10, second=0, microsecond=0)
      reason_3 = CLEAN_CO_CLEANING_NOT_DONE_BY_3_00
      reason_3_10 = CLEAN_CO_CLEANING_NOT_DONE_BY_3_10
      if nnow >= their_time_3 and not Message.objects.filter(
          work=cleaning, reason=reason_3).exists():
        # Can't count on this! Depends on properly webhooks
        if cleaning.accepted_by:
          content = '{} is still cleaning at {} and it\'s 3pm'.format(
              cleaning.accepted_by.name, building.nickname)
        else:
          content = 'The cleaning at {} is ongoing and it\'s 3pm'.format(
              building.nickname)
        message_sender.send(Message.objects.create(
            to=cleaning.get_work_co().alerts_email, reason=reason_3,
            kind=EMAIL, subject=reason_3, work=cleaning,
            content=content, when=nnow))
      elif nnow >= their_time_3_10 and not Message.objects.filter(
          work=cleaning, reason=reason_3_10).exists():
        message_sender.send(Message.objects.create(
            to=building.alerts_email, reason=reason_3_10,
            kind=EMAIL, subject=reason_3_10, work=cleaning,
            content=_simple_work_co_alert_content(cleaning), when=nnow))


def _simple_work_co_alert_content(cleaning):
  work_co = cleaning.get_work_co()
  return '{}\n\nRental: {}\nCleaning company: {} {}'.format(
      cleaning.keys_url(), cleaning.get_rental().nickname,
      work_co.name, work_co.alerts_email)


def send_independent_cleaning_taking_too_long_notifications(
    nnow=None, message_sender=None):
  """This is really about wanting to avoid over-paying hourly cleaners. Maybe
  they forgot to press the button to complete the job in Properly, maybe
  something weird went on and we want to dig into it.  We don't care if
  cleaning companies take too long exactly because they're paid a flat rate.
  """
  nnow = nnow or now()
  message_sender = message_sender or MessageSender()
  subject = SubjectLine.objects.get_subject_line(CLEANING_TAKING_TOO_LONG)
  for cleaning in Cleaning.objects.taking_too_long(nnow):
    if cleaning.uses_work_co():
      continue
    if not Message.objects.filter(
        reason=CLEANING_TAKING_TOO_LONG, work=cleaning).exists():
      rental = cleaning.rental
      # You can't count on accepted_by! It depends on properly webhooks.
      cleaner_text = ''
      cleaner = cleaning.accepted_by
      if cleaner:
        cleaner_text = ' to the cleaner {} at {}'.format(
            cleaner.name, cleaner.phone)

      content = (
          'The cleaning on {} at {} took/is taking longer than 3.5 hours to '
          'complete.\n\n'
          'Next steps:\n'
          '1. Reach out{} and see if the apartment '
          'was overly messy when they arrived.\n'
          '2. If the hours seem too far off, ask the cleaner if they '
          'stopped Properly at the end of the cleaning or if they forgot. '
          'If they left the clock running by accident, make a note of this '
          'so we can adjust the payout on Monday.').format(
              cleaning.get_full_start_time_str(), rental.full_address,
              cleaner_text)
      message_sender.send(Message.objects.create(
          to=rental.building.alerts_email, reason=CLEANING_TAKING_TOO_LONG,
          kind=EMAIL, subject=subject, content=content, work=cleaning,
          when=nnow))
      if cleaning.started_at:
        if nnow - cleaning.started_at >= timedelta(hours=3, minutes=45):
          log_error(
              'cleaning took too long email went out late',
              cleaning.keys_url())


def send_check_in_soon_notifications(nnow=None, message_sender=None):
  nnow = nnow or now()
  message_sender = message_sender or MessageSender()
  subject = SubjectLine.objects.get_subject_line(
      CLEANING_NOT_FINISHED_CHECK_IN_IN_25_MINUTES)
  for cleaning in Cleaning.objects.still_cleaning_25_before_checkin(nnow):
    if not Message.objects.filter(
        reason=CLEANING_NOT_FINISHED_CHECK_IN_IN_25_MINUTES,
        work=cleaning).exists():

      # You can't count on accepted_by! It depends on properly webhooks.
      cleaner_text = ''
      cleaner = cleaning.accepted_by
      if cleaner:
        cleaner_text = 'Worker name: {}\nWorker phone number: {}\n'.format(
            cleaner.name, cleaner.phone)

      following = cleaning.get_following_reservation()
      rental = cleaning.rental
      content = (
          'The cleaning below has not been finished and check-in begins at '
          '{}.\n\n{}'
          'Address: {}\n\n'
          'Next steps:\n'
          '1. Call or SMS the cleaner to ask when the cleaning will be '
          'done\n'
          '2. If the cleaning will not be done by 4 pm, send the guest who '
          'is checking in a message asking when they are arriving\n'
          '3. If the guest is arriving before the cleaning will be done, '
          'give the guest a heads up that the cleaner is still '
          'there.').format(
              following.check_in_time_string(),
              cleaner_text, rental.full_address)
      message_sender.send(Message.objects.create(
          to=rental.building.alerts_email,
          reason=CLEANING_NOT_FINISHED_CHECK_IN_IN_25_MINUTES,
          kind=EMAIL, subject=subject, content=content, work=cleaning,
          when=nnow))
      if following.check_in < nnow + timedelta(minutes=15):
        log_error(
            'CLEANING_NOT_FINISHED_CHECK_IN_IN_25_MINUTES went out late',
            'Check in at {} but sent at {}\n{}'.format(
                tz_dt_to_str(following.check_in), tz_dt_to_str(nnow),
                cleaning.keys_url()))


def send_unclaimed_cleaning_in_lt_x_hours(
    start_within_hours=48, reason=UNCLAIMED_CLEANING_IN_LT_48_HOURS,
    nnow=None, message_sender=None):
  nnow = nnow or now()
  message_sender = message_sender or MessageSender()
  for cleaning in Cleaning.objects.uh_oh_unclaimed(
      start_within_hours=start_within_hours, nnow=nnow):
    if cleaning.uses_work_co():
      # Work companies are covered by send_cleaning_unasigned
      continue
    if not Message.objects.filter(
        reason=reason, work=cleaning).exists():
      subject = SubjectLine.objects.get_subject_line(reason)
      accepted_at = '-'
      if cleaning.accepted_at:
        accepted_at = tz_dt_to_str(cleaning.accepted_at)
      content = (
          'The cleaning below is in less than {} hours that has not been '
          'accepted by any service providers.\n\n'
          'Now: {}\n'
          'Date of cleaning: {}\n'
          'Address: {}\n'
          'Keys url: {}\n'
          'Accepted by: {}\n'
          'Accepted at: {}\n'
          'Next steps: Reach out to the service providers in the area and '
          'see if anyone can handle the cleaning.').format(
              start_within_hours,
              tz_dt_to_str(nnow),
              cleaning.get_full_start_time_str(),
              cleaning.rental.full_address,
              cleaning.keys_url(),
              cleaning.accepted_by,
              accepted_at)
      message_sender.send(Message.objects.create(
          to=cleaning.rental.building.alerts_email,
          reason=reason, kind=EMAIL, subject=subject, content=content,
          work=cleaning, when=nnow))
