""" va knows about bgcheck. bgcheck knows about id_verify.

BackgroundCheck, like, criminal and sex offender background check.
Technology-wise, this is a fine project to work on, though
scrap_heap/authenticating/ was a big disappointment, being unable to automate
the process.

Nevertheless, this project is highly problematic.

What bothers me, for starters, is this code is precisely as racially biased as
the judicial system. Moving on, what in the world is this thing actually trying
to solve? Good luck getting a straight answer. I've heard a dozen theories that
mostly feel like marketing, "safety" and such. I'm unconvinced due to the
glaring loopholes. We only background check the person making the reservation,
so all your buddies can be felons and sex offenders without any problems. Or
you could pick an alias with a name and DOB with no criminal record associated
with it, sign up for Airbnb with your alias, and make a fake ID and credit card
to match. Or you could just commit your terrible crimes in a different country.
Or you could just not get caught. But whatever this thing accomplishes or
doesn't accomplish, it comes at a cost. As far as guest experience goes, it's
pure anti-feature. Plus there's lost profit due to any number of ways we can
lose reservations. We can fail to complete the check in time (or at all in the
case of people with common names), the guest could opt out, and of course,
guests may have a criminal background. So from where I'm sitting, this
requirement looks like a straight up liability.

So what IS this project really all about? Here's the real deal. The team really
really wants more units under management because they believe that's important
for getting investors. I'm also told that these units were somehow key
to getting units in other buildings because of some vague story involving some
lady with connections, or something. And this building is, quote, "Crime free"
because at the end of the day it's owned by some guy who obviously votes
Republican who's allowed to require background checks because Arizona. Also
apparently this is NOT our nicest property. I understand the view is of a
trailer park.

Meanwhile, we have a self-perception of being obsessed with hospitality. So
there's a bit of a disconnect there, which you expect in any venture whose real
goal is making money (organized religion for instance). You know how it goes.
The team will put an arm over your shoulder and tell you they don't really
BELIEVE in background checks and wish we didn't have to do them. But if you
threaten not to build this contraption they'll go blue in the face arguing how
reasonable it is to background check the guests in a naive attempt to get you
on board. Classic. But don't get too upset at them. They're just doing what
they think they gotta do to launch a company.

So listen, the leases are signed. My misgivings are noted. We'll do as good a
job as we reasonably can. Really our priorities here are, above all, don't get
sued. So if we're faced with a decision between doing a bad job completing a
background check vs canceling the reservation, cancel the reservation. If we
allow this hypothetical reservation and heaven forbid anything goes wrong,
we're liable.

Second priority is, don't let this thing snarl operations too bad. Final
priority, try not to let this cut into profits any more than necessary.  """

from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from errors.models import log_error, Notifier
from commands.models import background_command
from id_verify.models import (
    US_ID_FRONT_AND_BACK, PASSPORT, Submission, consent_to_bgcheck_paragraph)
from rentals.models import Building
from reservations.models import Reservation, CONFIRMED, CANCELED
from util.fields import OneToOneOrNoneField
from util.signals import post_sync
from util.table import Table, Cell
from util.timezone import dt_to_str, dt_to_date_str, now
from util.urls import keys_reverse


AUTHENTICATING = 'Authenticating'  # Automated. Doesn't work.
BEEN_VERIFIED = 'Been Verified'  # Manual.
PROVIDER_CHOICES = (
    (AUTHENTICATING, AUTHENTICATING),
    (BEEN_VERIFIED, BEEN_VERIFIED))


class BackgroundCheckAggregate(models.Model):
  """ Aggregated and hopefully therefore annonymized data about what the
  consequences of a background check policy were in a building
  per month. """
  building = models.ForeignKey(Building, on_delete=models.PROTECT)
  month = models.DateField(help_text='This should always be on the 1st')
  passes = models.PositiveIntegerField(default=0, help_text=(
      'How many background checks passed?'))
  canceled_due_to_fail = models.PositiveIntegerField(default=0, help_text=(
      'How many reservations did we have to cancel because a background check '
      'failed?'))
  opt_out = models.PositiveIntegerField(default=0, help_text=(
      'How many reservations did we have to cancel because the guest '
      'opted out of a background check?'))
  not_completed_in_time = models.PositiveIntegerField(default=0, help_text=(
      'How many reservations did we have to cancel because we couldnt '
      'complete the background check before check in?'))


class TimeToCompleteCheck(models.Model):
  month = models.DateField(help_text=(
      'What month did the background check start on? '
      'This should always be on the first of the month.'))
  seconds = models.PositiveIntegerField(help_text=(
      'How many seconds did it take to complete the background check?'))


class BackgroundCheckManager(models.Manager):
  def anonymize_old(self, nnow=None):
    """ We wanna drop this data like a hot potato! We have to hang on to fails
    for 60 days because guests can legally contest them. We have to hang on to
    passes until the end of the reservation so the table we present to the door
    person displays accurate info. """
    for check in BackgroundCheck.objects.select_related(
        'reservation', 'reservation__rental__building'):
      if check.can_discard(nnow=nnow):
        check_in_date = check.reservation.check_in
        month = date(check_in_date.year, check_in_date.month, 1)
        with transaction.atomic():
          aggregate = BackgroundCheckAggregate.objects.get_or_create(
              building=check.reservation.rental.building, month=month)[0]
          if check.not_completed_in_time:
            aggregate.not_completed_in_time += 1
          if check.submission and check.submission.opt_out_of_bgcheck:
            aggregate.opt_out += 1
          if check.passed:
            aggregate.passes += 1
          if check.passed is False:
            aggregate.canceled_due_to_fail += 1
          aggregate.save()
          check.delete()


ID_TYPE_CHOICES = (
    (PASSPORT, 'Passport'),
    (US_ID_FRONT_AND_BACK, 'US ID, front and back'))


class BackgroundCheck(models.Model):
  # As soon as we've got a confirmed reservation, I want a background check
  # object to talk about. Maybe it's a super last minute reservation and before
  # we even get a chance to try to collect a valid submission we realize we've
  # run out of time to do the check.
  reservation = OneToOneOrNoneField(Reservation, on_delete=models.PROTECT)
  # But in order for this to work we also need a submission object to talk
  # about as soon as a valid one is available because that's where we get
  # images from. This field is necessary as reservations often have multiple
  # submissions. It's nullable because no submission exists at first.
  submission = OneToOneOrNoneField(
      Submission, on_delete=models.PROTECT, null=True)

  provider = models.CharField(
      null=True, blank=True, max_length=100, choices=PROVIDER_CHOICES,
      default=AUTHENTICATING)
  passed = models.BooleanField(null=True, blank=True, help_text=(
      'Did the background check pass or fail?'))
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  got_valid_submission_at = models.DateTimeField(null=True, db_index=True)
  completed_at = models.DateTimeField(null=True, db_index=True)
  not_completed_in_time = models.BooleanField(default=False, help_text=(
      'If we cant complete the background check before check in, well have '
      'to cancel the reservation.'))
  time_to_complete_saved = models.BooleanField(default=False, help_text=(
      'Have we logged a TimeToCompleteCheck for this background check yet?'))

  def explain_why_cant_run_check(self, nnow=None):
    # If the id is manually marked verified, then no submission will ever
    # appear.
    if not self.reservation.id_verified and not self.submission:
      return 'No valid submission'

  def years_old(self, nnow=None):
    if self.submission:
      return self.submission.years_old(nnow=nnow)

  objects = BackgroundCheckManager()

  def status(self):
    if self.passed:
      return 'PASSED'
    elif self.passed is False:
      return 'FAILED'
    elif self.reservation.status == CANCELED and not self.submission:
      return 'UNNECESSARY'
    return 'INCOMPLETE'

  def save(self, *args, **kwargs):
    if int(bool(self.passed is not None)) + int(bool(self.completed_at)) == 1:
      raise Exception('Either set both or neither of passed and completed_at')
    super().save(*args, **kwargs)

  def set_passed(self, passed, provider=BEEN_VERIFIED):
    self.passed = passed
    self.provider = provider
    self.completed_at = now()
    self.save()

  def can_discard(self, nnow=None):
    nnow = nnow or now()
    if self.completed_at and self.passed is None:
      log_error(
          'Background check has weird state',
          'completed at {} passed {} pk {}'.format(
              self.completed_at, self.passed, str(self.pk)))
    past_checkout_date = nnow.date() > self.reservation.check_out.date()
    past_60_days = False
    if self.completed_at:
      past_60_days = self.completed_at + timedelta(days=60) <= nnow
    # You might not have a submission if the user hasn't submitted one yet, or
    # we're in tests.
    if self.submission and self.submission.opt_out_of_bgcheck:
      return self.reservation.canceled() or past_checkout_date
    elif self.not_completed_in_time:
      return self.completed_at
    elif self.passed:
      return past_checkout_date
    elif self.passed is False:
      return past_60_days
    return False

  def save_time_to_complete(self):
    if self.completed_at and not self.time_to_complete_saved:
      start_from = self.created_at
      if self.got_valid_submission_at:
        start_from = self.got_valid_submission_at
      diff = self.completed_at - start_from
      TimeToCompleteCheck.objects.create(
          month=date(self.completed_at.year, self.completed_at.month, 1),
          seconds=diff.days * 24 * 60 * 60 + diff.seconds)
      self.time_to_complete_saved = True
      self.save()

  def must_cancel(self, nnow=None):
    try:
      return must_cancel_reservations(nnow=nnow).filter(
          pk=self.reservation.pk).exists()
    except RecursionError:
      # No idea why this happened one time. I couldn't reproduce it in the
      # shell.
      log_error(
          'must_cancel RecursionError?!',
          'bgcheck {} has reservation {} called with nnow {}'.format(
              self.pk, self.reservation.pk, nnow))
      return self.reservation in must_cancel_reservations(nnow=nnow)

  def alert_must_cancel(self, notifier=None, nnow=None):
    # a.k.a. tests or production
    if notifier or settings.PROD:
      notifier = notifier or Notifier()
      if self.must_cancel(nnow=nnow):
        guest_name = self.reservation.guest.full_name
        subject = 'Please cancel and refund {}\'s reservation'.format(
            guest_name)
        message = (
            'We are obligated to cancel this reservation and offer a full '
            'refund.\n\n{}\n(no longer) checking in on {}\n{}').format(
                guest_name,
                dt_to_str(self.reservation.get_check_in()),
                self.reservation.admin_url())
        notifier.notify(settings.ALERT_MUST_CANCEL, subject, message=message)

  def alert_bgcheck_required(self, notifier=None, nnow=None):
    # a.k.a. tests or production
    if notifier or settings.PROD:
      notifier = notifier or Notifier()
      if self.passed is None and not self.explain_why_cant_run_check():
        guest_name = self.reservation.guest.full_name
        subject = (
            'A background check is required for {}\'s '
            'reservation'.format(guest_name))
        message = 'Check in {}'.format(
            dt_to_str(self.reservation.get_check_in()))
        if not self.submission:
          message += (
              '\n\nThe guest does not have a valid ID submission, so you\'ll '
              'need to contact them and ask if it\'s ok to run a background '
              'check on them. It\'s best if you use the exact language from '
              'the ID verification page:\n\n')
          message += consent_to_bgcheck_paragraph()
          message += (
              '\n\nThen you\'ll need to find out their birthday and full '
              'legal name for the background check process.')
        message += '\n\n{}'.format(keys_reverse('bgcheck'))
        notifier.notify(
            settings.ALERT_BGCHECK_REQUIRED, subject, message=message)

  def alert_if_not_reservation_submission(self):
    if self.reservation and self.submission and (
        self.reservation != self.submission.reservation):
      if settings.TEST:
        raise Exception('The reservation and submission dont match.')
      log_error((
          'The reservation and submission dont match for '
          'BackgroundCheck {}').format(self.pk))


MANUAL_ID_VERIFICATION = (
    'The ID was verified manually. No valid submission exists')


@receiver(post_sync, sender=Reservation)
def post_sync_reservation(sender, instance, *args, **kwargs):
  nnow = kwargs.get('nnow', now())
  if instance.confirmed() and instance.check_out > nnow and (
      instance.background_check_required()):
    BackgroundCheck.objects.get_or_create(reservation=instance)


@receiver(post_save, sender=Submission)
def post_save_submission(sender, instance, *args, **kwargs):
  if (instance.all_good() or instance.opt_out_of_bgcheck) and (
      instance.reservation.backgroundcheck_or_none):
    existing_check = instance.reservation.backgroundcheck
    if existing_check.completed_at:
      return
    existing_submission = existing_check.submission
    if existing_submission:
      this_is_newer = instance.opt_out_of_bgcheck or instance.checked_at and (
          not existing_submission.checked_at or (
              instance.checked_at > existing_submission.checked_at))
      if this_is_newer:
        existing_check.submission = instance
    else:
      existing_check.submission = instance
    existing_check.got_valid_submission_at = (
        existing_check.got_valid_submission_at or now())
    existing_check.save()


@receiver(post_save, sender=BackgroundCheck)
def post_save_background_check(sender, instance, *args, **kwargs):
  instance.save_time_to_complete()
  notifier = kwargs.get('notifier', None)
  nnow = kwargs.get('nnow', None)
  instance.alert_must_cancel(notifier, nnow=nnow)
  instance.alert_bgcheck_required(notifier, nnow=nnow)
  instance.alert_if_not_reservation_submission()


@background_command
def must_cancel_daily_notification_background(notifier=None, nnow=None):
  notifier = notifier or Notifier()
  must_cancels = must_cancel_reservations(nnow=nnow)
  if must_cancels.exists():
    subject = '{} reservation(s) must still be canceled and refunded'.format(
        must_cancels.count())
    message = keys_reverse('must_cancel')
    notifier.notify(settings.ALERT_MUST_CANCEL, subject, message=message)


@background_command
def bgcheck_required_daily_notification_background(
    notifier=None, nnow=None):
  notifier = notifier or Notifier()
  required = bgchecks_for_vas(nnow=nnow)
  if required.exists():
    subject = '{} reservation(s) require background checks'.format(
        required.count())
    message = keys_reverse('bgcheck')
    notifier.notify(
        settings.ALERT_BGCHECK_REQUIRED, subject, message=message)


def check_for_run_out_of_time(nnow=None):
  nnow = nnow or now()
  # Check ins are at 4pm, the guest shows up in the door person list at
  # 12:00:01am, and we want to give 24 hours notice before that. So that's 16 +
  # 24 = 40hrs.
  for check in BackgroundCheck.objects.filter(
      reservation__check_in__lte=nnow + timedelta(hours=6),
      reservation__check_out__gte=nnow,  # Forget ancient history
      reservation__rental__building__background_check_guests=True,
      reservation__status=CONFIRMED, completed_at__isnull=True):
    check.not_completed_in_time = True
    check.save()


def reservations_for_door_person(building, nnow=None):
  nnow = nnow or now()
  return Reservation.objects.filter(
      rental__building=building, check_in__date__lte=nnow.date(),
      check_out__date__gte=nnow.date(), status=CONFIRMED)


def door_person_table(reservations):
  table = Table([
      'Guest', 'Unit', 'Check in', 'Check out', 'Background check passed on'])
  for reservation in reservations:
    check_in = dt_to_str(reservation.get_check_in())
    check_out = dt_to_str(reservation.get_check_out())
    bg_passed_on = None
    # This had better be true or we're in breach of contract.
    if reservation.backgroundcheck_or_none and (
        reservation.backgroundcheck.completed_at):
      bg_passed_on = dt_to_date_str(
          reservation.tz_dt_to_tz_dt(reservation.backgroundcheck.completed_at))
    table.create_row([
        reservation.guest.full_name, reservation.rental.nickname, check_in,
        check_out, bg_passed_on])
  return table


def must_cancel_reservations(nnow=None):
  nnow = nnow or now()
  reasons = Q(backgroundcheck__passed=False) | Q(
      backgroundcheck__submission__opt_out_of_bgcheck=True) | Q(
          backgroundcheck__not_completed_in_time=True,
          backgroundcheck__passed__isnull=True)
  return Reservation.objects.filter(
      reasons, status=CONFIRMED, check_out__gte=nnow)


def must_cancel_reservations_table(reservations):
  table = Table([
      'Reservation in Guesty', 'Reservation in Keys', 'Guest', 'Check in',
      'Channel'])
  for res in reservations:
    table.create_row([
        Cell(res.channel_id, url=res.admin_url()),
        Cell(res.pk, url=res.res_deets_url_no_server()),
        res.guest.full_name, res.check_in, res.channel])
  return table


def bgchecks_for_vas(nnow=None):
  """ Which background checks matter to the VAs? Those that are incomplete or
  recently complete for reservations that haven't checked out. """
  nnow = nnow or now()
  not_complete = Q(backgroundcheck__passed__isnull=True)
  # Just in case a VA incorrectly sets the passed field, show it for a bit
  # after it's set so they can correct it if need be.
  recently_complete = Q(
      backgroundcheck__completed_at__gt=nnow - timedelta(hours=1))
  not_or_recently_complete = not_complete | recently_complete
  return Reservation.objects.filter(
      not_or_recently_complete, backgroundcheck__isnull=False,
      status=CONFIRMED, check_out__gte=nnow)


def bgcheck_reservations_table(reservations, nnow=None):
  nnow = nnow or now()
  table = Table([
      'Guest', 'Age', 'Legal name', 'Check in', 'Guesty', 'Keys',
      'ID front', 'ID back', 'Passed', 'Mark passed', 'Mark not passed',
      'Explain why can\'t check', 'First appeared', 'Became checkable'])
  for res in reservations:
    guesty_cell = Cell(res.channel_id, url=res.admin_url())
    keys_cell = Cell(res.pk, url=res.res_deets_url_no_server())
    check = res.backgroundcheck
    front = None
    back = None
    legal_name = None
    if check.submission:
      front = Cell(img_url=check.submission.id_photo_url())
      back = Cell(img_url=check.submission.id_back_url())
      legal_name = check.submission.legal_name
    explain_why_cant = check.explain_why_cant_run_check()
    passed = None
    failed = None
    if not explain_why_cant:
      passed = _mark_passed_button(check, True)
      failed = _mark_passed_button(check, False)
    table.create_row([
        Cell(res.guest.full_name, classes=['guest_name']),
        check.years_old(nnow=nnow), legal_name,
        res.check_in.date(), guesty_cell, keys_cell, front, back,
        Cell(check.passed, classes=['passed']),
        passed, failed, explain_why_cant, check.created_at,
        check.got_valid_submission_at])
  return table


def _mark_passed_button(bgcheck, set_passed_to):
  text = 'Passed' if set_passed_to else 'Did not pass'
  return (
      '<button data-id="{}" data-value="{}" class="mark_passed">'
      '{}</button>').format(bgcheck.pk, set_passed_to, text)


class DoorPerson(models.Model):
  """ They stand at the door of a building, consult the list of guests, and
  greet them by name. Also they can see that everybody (hopefully) passed a
  background check. """
  building = models.ForeignKey(Building, on_delete=models.CASCADE)
  user = OneToOneOrNoneField(User, on_delete=models.CASCADE)

  def reservations(self, nnow=None):
    return reservations_for_door_person(self.building, nnow=nnow)
