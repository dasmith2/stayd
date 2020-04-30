from collections import namedtuple

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from errors.models import log_error, Notifier
from id_verify.models.submission import Submission
from reservations.models import Reservation, CONFIRMED, INQUIRY
from util import twilio
from util.background import background
from util.channels import AIRBNB
from util.fields import OneToOneOrNoneField
from util.signals import keys_post_save
from util.table import Table, Cell
from util.timezone import now


DECLINE_WHEN_OVER = 75
ACCEPT_WHEN_UNDER = 39


def should_decline(score):
  return score > DECLINE_WHEN_OVER


def should_accept(score):
  return score < ACCEPT_WHEN_UNDER


def should_escalate(score):
  return not should_decline() and not should_accept()


@receiver(post_save, sender=Reservation)
def post_save_reservation(sender, instance, *args, **kwargs):
  RiskScore.objects.get_or_create(reservation=instance)


@receiver(keys_post_save, sender=Submission)
def keys_post_save_submission(sender, instance, *args, **kwargs):
  nnow = kwargs.get('nnow', None)
  if instance.reservation and instance.all_good():
    post_save_reservation(Reservation, instance.reservation, nnow=nnow)
    risk_score = instance.reservation.riskscore
    risk_score.submission = instance
    risk_score.save(**kwargs)
    if risk_score.is_voip is None and risk_score.phone():
      _calc_is_voip(
          risk_score, has_is_voip=kwargs.get('has_is_voip', None),
          syncer=kwargs.get('syncer', None))


@background
def _calc_is_voip(risk_score, has_is_voip=None, syncer=None):
  if has_is_voip is None:
    # Local web tests.
    if settings.LOCAL and settings.RUNSERVER:
      risk_score.is_voip = False
      risk_score.save(syncer=syncer)
      return
  has_is_voip = has_is_voip or twilio

  risk_score.is_voip = has_is_voip.is_voip(risk_score.phone())
  risk_score.save(syncer=syncer)
  if risk_score.pushed_score is None:
    log_error('How did this risk score not push?', (
        'Risk score {} for reservation {} SHOULD have everything it needs '
        'at this point to calculate and push a score, but the pushed_score '
        'is {}. {}.').format(
            risk_score.pk, risk_score.reservation.keys_url(),
            risk_score.pushed_score,
            risk_score.explain_why_cant_calculate_score()))


ScoreFactor = namedtuple('ScoreFactor', 'score description')


def high_risk_reservations_table(reservations):
  table = Table([
      'Action', 'Guesty', 'Keys', 'Guest', 'Risk score', 'Factors',
      'Paid in so far', 'Check in', 'Channel'])
  for reservation in reservations:
    approve_button = (
        '<button type="submit" name="reservation_id" value="{}">'
        'Approve</button>').format(reservation.pk)
    guesty = Cell('guesty', url=reservation.admin_url())
    keys = Cell('keys', url=reservation.res_deets_url_no_server())
    risk_score = reservation.riskscore
    factors = ''
    if risk_score.can_calculate_score():
      factors = '. '.join([
          factor.description for factor in risk_score.score_factors()])
    table.create_row([
        Cell(html_content=approve_button), guesty, keys,
        reservation.guest.get_name(),
        risk_score.pushed_score, factors,
        reservation.actual_payin, reservation.check_in,
        reservation.channel])
  return table


def high_risk_reservations_for_vas():
  return Reservation.objects.filter(
      Q(status=CONFIRMED) | Q(status=INQUIRY),
      riskscore__pushed_score__gt=ACCEPT_WHEN_UNDER,
      riskscore__reservation_approved_by__isnull=True).select_related(
          'guestyreservation', 'rental', 'guest',
          'riskscore', 'riskscore__submission').order_by('-check_in')


class RiskScore(models.Model):
  reservation = OneToOneOrNoneField(Reservation, on_delete=models.CASCADE)
  submission = OneToOneOrNoneField(
      Submission, null=True, blank=True, on_delete=models.PROTECT, help_text=(
          'What valid submission are we basing this risk score off of?'))
  created_at = models.DateTimeField(auto_now_add=True)
  is_voip = models.NullBooleanField(
      null=True, blank=True, help_text=(
          'Does the guest have a voice over IP (voip, a.k.a. virtual) phone '
          'number? I store this because it requires an API call.'))
  pushed_score = models.IntegerField(null=True, blank=True, help_text=(
      'If we called syncer.set_risk_score, what value did we give it for this '
      'reservation?'))
  notified_of_high_risk_at = models.DateTimeField(null=True, help_text=(
      'If this is a high risk reservation, when did we send an email '
      'notifying the team of that?'))
  reservation_approved_by = models.ForeignKey(
      User, on_delete=models.PROTECT, null=True, blank=True, help_text=(
          'If this is a high or moderate risk reservation, it will '
          'need somebody to sign off on it.'))
  reservation_approved_at = models.DateTimeField(null=True, help_text=(
      'When was this medium or high risk reservation approved?'))

  def save(self, *args, **kwargs):
    if int(bool(self.reservation_approved_by)) + (
        int(bool(self.reservation_approved_at))) == 1:
      raise Exception(
          'Specify both or neither of reservation_approved_by and '
          'reservation_approved_at')
    super().save()
    self.possibly_push_score(**kwargs)
    self.possibly_notify(**kwargs)

  def reservation_requires_approval(self):
    return self.high_risk() or self.medium_risk()

  def reservation_approved(self):
    return self.low_risk() or self.reservation_approved_by

  def possibly_push_score(self, **kwargs):
    syncer = kwargs.get('syncer', None)
    if syncer is None:
      if settings.LOCAL and settings.RUNSERVER:
        pass  # Webtest.
      else:
        syncer = self.reservation.get_syncer()
    if self.can_calculate_score():
      score = self.score()
      if self.pushed_score != score:
        if syncer:
          syncer.set_risk_score(self.reservation, score)
        self.pushed_score = score
        self.save(**kwargs)

  def possibly_notify(self, **kwargs):
    nnow = kwargs.get('nnow', None) or now()
    notifier = kwargs.get('notifier', None) or Notifier()
    if self.can_calculate_score():
      score = self.score()
      if (self.medium_risk() or self.high_risk()) and (
          self.notified_of_high_risk_at is None):
        self.notified_of_high_risk_at = nnow
        self.save(**kwargs)
        guest_name = self.reservation.guest.get_name()
        subject = 'Alert: {} is a high risk reservation'.format(guest_name)
        factors = self.score_factors(nnow=nnow)
        factors_str = '\n'.join([
            '{}: {}'.format(fctr.description, fctr.score) for fctr in factors])
        message = '{}\n\n{}\n\nTotal risk score: {}'.format(
            self.reservation.keys_url(), factors_str, score)
        notifier.notify(settings.ALERT_HIGH_RISK_RESERVATION, subject, message)

  def high_risk(self):
    return self.pushed_score and should_decline(self.pushed_score)

  def medium_risk(self):
    return self.pushed_score and not self.high_risk() and not self.low_risk()

  def low_risk(self):
    return self.pushed_score and should_accept(self.pushed_score)

  def phone(self):
    return self.submission.reservation.guest.phone_with_country_code()

  def years_old(self, nnow=None):
    if self.submission:
      return self.submission.years_old(nnow=nnow)

  def can_calculate_score(self):
    return not self.explain_why_cant_calculate_score()

  def explain_why_cant_calculate_score(self):
    if not self.submission:
      return 'This reservation doesnt have a valid submission yet'
    if self.submission.has_negative_reviews is None:
      return 'I don\'t know if the guest has negative reviews'
    if self.submission.booking_for_themself is None:
      return 'I don\'t know if the guest booked for themself\'s'
    if self.submission.explained_trip is None:
      return 'The submission is missing explained_trip'
    if self.submission.positive_reviews is None:
      return 'The submission is missing positive_reviews'
    if self.is_voip is None:
      if not self.phone():
        return (
            'The guest doesnt have a phone number so I cant look up whether '
            'or not its voip')
      else:
        return (
            'I havent looked up whether or not the guests phone number is '
            'voip')
    if not self.submission.birthday:
      return 'I don\'t know how old the guest is'
    if self.submission.lives_nearby is None:
      return 'I don\'t know if the guest lives nearby'
    if self.reservation.guest_count is None:
      return 'I don\'t know how many guests are staying'

  def score(self):
    factors = self.score_factors()
    if factors:
      return sum([factor.score for factor in factors])
    return 0

  def _raise_if_cant_calc(self):
    why_cant_calc = self.explain_why_cant_calculate_score()
    if why_cant_calc:
      raise Exception(
          'I cant calculate the risk score factors because {}'.format(
              why_cant_calc))

  def score_factors_as_table(self, nnow=None):
    table = Table(['Factor', 'Score'])
    if self.can_calculate_score():
      for factor in self.score_factors(nnow=nnow):
        table.create_row([factor.description, factor.score])
    return table

  def score_factors(self, nnow=None):
    self._raise_if_cant_calc()

    factors = []

    if self.reservation.channel != AIRBNB:
      factors.append(ScoreFactor(5, 'The channel is {}'.format(
          self.reservation.channel)))
    if self.submission.has_negative_reviews:
      factors.append(ScoreFactor(100, 'The guest has negative reviews'))
    if not self.submission.booking_for_themself:
      factors.append(ScoreFactor(
          10, 'The person who booked isn\'t the person who\'s staying'))
    if not self.submission.explained_trip:
      factors.append(ScoreFactor(
          10, 'The guest didn\'t explain the purpose of their trip'))

    if self.submission.positive_reviews == 0:
      factors.append(ScoreFactor(10, 'The guest has 0 positive reviews'))
    elif self.submission.positive_reviews == 1:
      pass
    else:
      diff = -10
      if self.submission.positive_reviews <= 4:
        diff = -5
      elif self.submission.positive_reviews <= 10:
        diff = -7
      factors.append(ScoreFactor(
          diff, 'The guest has {} positive reviews'.format(
              self.submission.positive_reviews)))

    if self.is_voip:
      factors.append(ScoreFactor(40, 'The guest has a VOIP phone number'))
    if self.submission.years_old(nnow=nnow) < 25:
      factors.append(ScoreFactor(40, 'The guest is only {} years old'.format(
          self.submission.years_old())))
    if self.submission.lives_nearby:
      factors.append(ScoreFactor(75, 'The guest lives nearby'))

    if self.reservation.guest_count >= 5:
      diff = 10
      if self.reservation.guest_count == 5:
        diff = 5
      factors.append(ScoreFactor(diff, 'This reservation has {} guests'.format(
          self.reservation.guest_count)))

    if self.reservation.get_night_count() <= 2:
      diff = 10
      if self.reservation.get_night_count() == 1:
        diff = 15
      factors.append(ScoreFactor(
          diff, 'The reservation is only {} nights long'.format(
              self.reservation.get_night_count())))

    weekday = self.reservation.check_in.date().weekday()
    if weekday in [4, 5]:
      factors.append(ScoreFactor(20, 'The reservation starts on a {}'.format(
          ['Friday', 'Saturday'][weekday - 4])))

    booked_in_advance = self.reservation.booked_days_in_advance()
    if booked_in_advance == 0:
      factors.append(ScoreFactor(15, 'Same day reservation'))
    elif booked_in_advance != 4:
      description = 'Booked {} days in advance'.format(booked_in_advance)
      diff = -5
      if booked_in_advance <= 3:
        diff = 10
      factors.append(ScoreFactor(diff, description))

    # haha old school blacklist. These were manually in the typeform. These
    # will be replaced by the guest blacklist project.
    guest_name = self.reservation.guest.full_name
    if guest_name.lower() in ['james avery', 'ildefonso colon']:
      factors.append(ScoreFactor(1000, '{} is blacklisted'.format(guest_name)))

    return factors
