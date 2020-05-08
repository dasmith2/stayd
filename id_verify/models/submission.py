import ast
from datetime import timedelta
import time

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django.shortcuts import reverse

from errors.models import log_error
from guest_messages.models.sms import SMS, SMSTemplate
from guest_messages.models.message import (
    LAST_NAME_ID_RES_DO_NOT_MATCH, FIRST_LAST_NAME_ID_CC_DO_NOT_MATCH,
    LAST_4_BRAND_CC_RES_DO_NOT_MATCH, NO_NAMES_MATCH,
    LAST_NAME_ID_RES_LAST_4_BRAND_CC_DO_NOT_MATCH,
    FULL_NAME_CC_ID_LAST_4_BRAND_CC_DO_NOT_MATCH, CC_ID_EVERYTHING_WRONG,
    GUEST_UPLOADED_US_ID_FRONT_ONLY,
    GUEST_UPLOADED_NON_US_ID)
from reservations.models.money import (
    Reservation, get_reservation_from_query, CONFIRMED)
from reservations.syncer import ReservationManagerIsDown
from util.background import background
from util.channels import (
    THEY_ASSUME_CC_RISK_CHANNELS, THEY_TAKE_SECURITY_DEPOSIT,
    cc_photo_required)
from util.email import EmailSender
from util.signals import keys_post_save, post_sync
from util.timezone import now, years_old


def consent_to_bgcheck_paragraph():
  return """
      <p class="description">This property requires a <b>background
      screening</b>. If you are not comfortable with a background screening, we
      will cancel your reservation and give you a full refund.</p>
      <p class="description">NOTE: In accordance with the Fair Credit Reporting
      Act we are notifying you that we conduct background criminal inquiries
      through an independent Consumer Reporting Agency. In the event we find
      you have had a prior conviction of a felony, you will not qualify as a
      guest for this property, and you will be given a full refund. By clicking
      the "I consent" button below, you acknowledge and provide consent to a
      background check.</p>"""


ID = 'ID'
BACK_OF_ID = 'BACK_OF_ID'
CC = 'CC'


class SubmissionManager(models.Manager):
  def all_good(self, reservation):
    return any([sub.all_good() for sub in reservation.submission_set.all()])

  def match_reservations_to_reservationless_submissions(
      self, syncer=None, email_sender=EmailSender(), verbose=False):
    for submission in Submission.objects.filter(
        created_at__gt=now() - timedelta(days=3), reservation__isnull=True):
      useful_dict = {}
      # query string dicts do values as lists.
      for key, value in ast.literal_eval(submission.query).items():
        if isinstance(value, list):
          value = value[0]
        useful_dict[key] = value
      reservation = get_reservation_from_query(useful_dict)
      if reservation:
        if verbose:
          print(
              'Matching submission {} up to reservation {} based on {}'.format(
                  submission.pk, reservation.pk, submission.query))
        submission.reservation = reservation
        submission.save()
        post_submission_steps_background(
            submission_pk=submission.pk, syncer=syncer,
            email_sender=email_sender)
      elif verbose:
        print('Unable to find a match for query string {}'.format(
            submission.query))

  def checkable_submissions(self, escalated=None):
    last_4_is_not_null = Q(reservation__cc_last_4__isnull=False)
    no_cc_necessary = Q(
        reservation__channel__in=THEY_ASSUME_CC_RISK_CHANNELS) & Q(
        reservation__channel__in=THEY_TAKE_SECURITY_DEPOSIT)
    checkable = self.filter(
        last_4_is_not_null | no_cc_necessary,
        id_matches_res__isnull=True, resized=True,
        created_at__gt=now() - timedelta(days=30), reservation__isnull=False,
        reservation__status=CONFIRMED, reservation__id_verified=False)
    if escalated is not None:
      checkable = checkable.filter(escalated=escalated)
    return checkable


def unprocessed_post_submission_steps(nnow=None):
  nnow = nnow or now()
  return Submission.objects.filter(
      post_submission_steps_at__isnull=True, reservation__isnull=False,
      created_at__gte=nnow - timedelta(days=30))


@background
def post_submission_steps_background(
    submission_pk=None, syncer=None, email_sender=EmailSender(),
    verbose=False):
  if submission_pk:
    submissions = [Submission.objects.get(pk=submission_pk)]
  else:
    submissions = unprocessed_post_submission_steps()
  for submission in submissions:
    if verbose:
      print((
          'Settings custom fields, resizing, and notifying admins for '
          'submission {}').format(submission.pk))
    if settings.TEST or settings.PROD:
      # Stage needs to run the system test but stage can't write to Guesty, so
      # unfortunately we have to leave this little bit out in that case. Prod
      # can do it because it has permission and tests can because the api is
      # mocked (if it isn't, it raises an exception at the guesty/api.py level)
      syncer = syncer or submission.reservation.get_syncer()
      success = False
      for i in range(3):
        if not success:
          try:
            syncer.set_phone_email(
                submission.reservation, submission.phone, submission.email)
            success = True
          except ReservationManagerIsDown as ex:
            if i == 2:
              raise ex
            else:
              time.sleep(1)
    subject = 'ID submitted for verification'
    url = reverse('submissions')
    if submission.reservation.cc_action_required():
      subject = 'ID submitted, but there\'s a payment problem'
      url = reverse('cc_action_required')
    email_sender.send_mail(
        subject,
        settings.VERIFY_ID_SERVER + url,
        'heroku@stayd.com', settings.ALERT_NEW_ID_SUBMISSION)
    submission.post_submission_steps_at = now()
    submission.save()


@background
def post_check_id_steps(submission_pk, front, syncer=None):
  submission = Submission.objects.get(pk=submission_pk)
  if syncer is None:
    if settings.LOCAL and settings.RUNSERVER:
      pass  # Webtest
    else:
      syncer = submission.reservation.get_syncer()
  if submission.all_good():
    submission.reservation.id_verified = True
    submission.reservation.save()
    if syncer:
      syncer.set_id_verified(submission.reservation)
  else:
    submission.send_follow_up_message(front)
  submission.checked_at = now()
  submission.save()

  if submission.all_good():
    # Cleanings wait for a valid submission.
    post_sync.send(sender=Reservation, instance=submission.reservation)


US_ID_FRONT_ONLY = 'us_id_front_only'
NON_US_ID = 'non_us_id'
PASSPORT = 'passport'
US_ID_FRONT_AND_BACK = 'us_id_front_and_back'

ID_TYPE_CHOICES = (
    (PASSPORT, 'Passport'),
    (US_ID_FRONT_AND_BACK, 'US ID, front and back'),
    (US_ID_FRONT_ONLY, 'US ID, front only'),
    (NON_US_ID, 'Non-US ID'))


class Submission(models.Model):
  """ This class represents a single submission of the id verification
  form. The photo is passed directly to our bucket on Amazon's S3 via
  Javascript because Django is a single threaded web framework. That means a
  file upload blocks the thread until it's done, so it's a bad idea to pass all
  the bytes of a big ol' user submitted image through the app itself, because
  that would block all incoming requests.

  There are 3 possible states. 1. The user just uploaded a photo. It's on S3,
  resized=False. 2. The compressor went through, renamed, and resized this
  submission's photos. Now resized=True. 3. We deleted the photos because
  they're a huge security liability. Now resized is irrelevant and the
  SubmissionPhotos are removed. """
  query = models.CharField(max_length=200, default='', help_text=(
      'We collect this no matter what in case we can\'t automatically '
      'figure out what reservation this is for.'))
  unique_form_id = models.CharField(max_length=10, default='', help_text=(
      'This is just for detecting when the user hits refresh and submits '
      'the same form twice. Without this check, youll probably get a 404 '
      'as the second submission tries to resize its photos which have been '
      'resized in the meantime by the previous submission.'))
  email = models.CharField(max_length=100, default='')
  opt_in_email = models.BooleanField(help_text=(
      'The guest checked a box saying its ok to contact them about discounted '
      'future stays via email. Note, they didnt agree to being contacted for '
      'any other reason, so resist the temptation!'))
  phone = models.CharField(max_length=100, blank=True, default='', help_text=(
      'The channels have already collected a phone number for us. This '
      'optional phone number is specifically what they typed as the best '
      'number to text them at while they\'re traveling if it\'s not the '
      'phone they provided already.'))
  opt_in_texts = models.BooleanField(help_text=(
      'The guest checked a box saying its ok to contact them about discounted '
      'future stays via SMS. Note, they didnt agree to being contacted for '
      'any other reason, so resist the temptation!'))
  resized = models.BooleanField(default=False, help_text=(
      'Users will be uploading huge photos, I\'m sure. The '
      'id_verify.compressor goes through and shrinks them.'))
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  reservation = models.ForeignKey(
      Reservation, on_delete=models.CASCADE, null=True, help_text=(
          'This can be null because sometimes we might get a submission '
          'before janky Guesty sends us a webhook and we need to go back '
          'through and match them up.'))
  id_matches_res = models.NullBooleanField(
      null=True, blank=True, help_text=(
          'Does the last name on the ID match the last name of the person who '
          'made the reservation? Required for all reservations.'))

  has_negative_reviews = models.NullBooleanField(
      null=True, blank=True, help_text=(
          'Does the guest have any negative reviews on the channel they '
          'booked on?'))
  positive_reviews = models.PositiveIntegerField(
      null=True, blank=True, help_text=(
          'How many positive reviews does the guest have on the channel they '
          'booked on?'))
  booking_for_themself = models.NullBooleanField(
      null=True, blank=True, help_text=(
          'Is the person making the reservation the person actually staying '
          'in the rental, or are they booking for somebody else?'))
  explained_trip = models.NullBooleanField(
      null=True, blank=True, help_text=(
          'When the guest booked on the channel, did they include a message '
          'explaining the reason for their trip?'))
  lives_nearby = models.NullBooleanField(
      null=True, blank=True, help_text=(
          'Does the guest live within a 45 mile drive of the rental?'))
  # Background check stuff. bgcheck requires us to collect some additional
  # information from the guest. Those go here. Tests in this app should simply
  # verify that we were able to collect all the info we needed. What doesn't go
  # here is any logic about what to do with these fields.
  birthday = models.DateField(null=True, blank=True, help_text=(
      'This is used by background checks and risk scores.'))
  legal_name = models.CharField(
      max_length=200, default='', blank=True, help_text=(
          'What does their ID say their full name is?'))
  id_type = models.CharField(
      max_length=100, blank=True, default='', choices=ID_TYPE_CHOICES,
      help_text='What did the VA say the type of ID was?')
  opt_out_of_bgcheck = models.BooleanField(default=False, help_text=(
      'Did the guest opt out of a background check?'))

  cc_matches_id = models.NullBooleanField(
      null=True, blank=True, help_text=(
          'Do the first and last names on the ID match the first and last '
          'names on the credit card? This only applies on reservations where '
          'we assume credit card risk like Booking.com'))
  cc_matches_payment = models.NullBooleanField(
      null=True, blank=True, help_text=(
          'Do the last 4 digits of the cc and the type of cc match the card '
          'used to make the reservation? This only applies on reservations '
          'where we assume credit card risk like Booking.com'))
  checked_at = models.DateTimeField(null=True, blank=True)
  # null=True because this field is new and we don't know who checked all the
  # old submissions.
  checked_by = models.ForeignKey(
      User, null=True, on_delete=models.PROTECT, help_text=(
          'Sometimes mistakes get made. Now we know who to go coach.'))
  risk_score = models.IntegerField(null=True, blank=True, help_text=(
      'No longer used! Calculate this guest\'s risk score using '
      'https://bit.ly/2YSqlTy and enter it here'))
  post_submission_steps_at = models.DateTimeField(
      null=True, blank=True, help_text=(
          'When did the post-submission steps such as resizing occur?'))
  escalated = models.BooleanField(default=False, help_text=(
      'When a submission is just too weird, they photographed their pet, '
      'say. Now a higher up has to deal with it.'))
  escalated_by = models.CharField(
      max_length=200, null=True, blank=True, help_text=(
          'Sometimes admins incorrectly escalate a submission. Now we '
          'know who to go coach.'))

  objects = SubmissionManager()

  def save(self, *args, **kwargs):
    if self.all_good():
      if not (self.checked_at and self.checked_by):
        raise Exception(
            'This Submission is all_good, but you either didnt specify '
            'checked_at or checked_by.')
      if not self.birthday:
        raise Exception('Birthday is always required now')
    super().save()
    keys_post_save.send(sender=Submission, instance=self, *args, **kwargs)

  def years_old(self, nnow=None):
    if self.birthday:
      return years_old(self.birthday, nnow)

  def background_check_required(self):
    return self.reservation.background_check_required()

  def all_good(self):
    if not self.reservation or not self.id_matches_res:
      return False
    if self.reservation.we_assume_cc_risk():
      if not self.cc_matches_id or not self.cc_matches_payment:
        return False
    if self.background_check_required():
      if self.id_type not in [PASSPORT, US_ID_FRONT_AND_BACK]:
        return False
    return True

  def send_follow_up_message(self, front):
    triggering_event = self._get_triggering_event_by_problem()
    if not triggering_event:
      raise Exception(
          'Couldnt determine the triggering event for sending a follow up '
          'message')
    template = SMSTemplate.objects.filter(
        triggering_event=triggering_event).first()
    if template:
      message = template.create_new_message(self.reservation)
      SMS.objects.send(message_pk=message.pk, front=front)
    else:
      log_error('Template with triggering_event {} doesnt exist'.format(
          triggering_event))

  def _get_triggering_event_by_problem(self):
    if self.reservation.we_assume_cc_risk():
      if not self.id_matches_res:
        if not self.cc_matches_id:
          if not self.cc_matches_payment:
            return CC_ID_EVERYTHING_WRONG
          return NO_NAMES_MATCH
        if not self.cc_matches_payment:
          return LAST_NAME_ID_RES_LAST_4_BRAND_CC_DO_NOT_MATCH
        return LAST_NAME_ID_RES_DO_NOT_MATCH
      if not self.cc_matches_id:
        if not self.cc_matches_payment:
          return FULL_NAME_CC_ID_LAST_4_BRAND_CC_DO_NOT_MATCH
        return FIRST_LAST_NAME_ID_CC_DO_NOT_MATCH
      if not self.cc_matches_payment:
        return LAST_4_BRAND_CC_RES_DO_NOT_MATCH
    elif not self.id_matches_res:
      return LAST_NAME_ID_RES_DO_NOT_MATCH
    if self.id_type == US_ID_FRONT_ONLY:
      return GUEST_UPLOADED_US_ID_FRONT_ONLY
    elif self.id_type == NON_US_ID:
      return GUEST_UPLOADED_NON_US_ID
    return None

  def was_checked(self):
    return self.id_matches_res is not None

  def explain_why_not_check(self):
    if not self.reservation:
      return 'We don\'t know what reservation this submission is for yet.'
    if self.reservation.id_verified:
      return 'The ID is verified already for this reservation.'
    channel = self.reservation.channel
    no_last_4 = self.reservation.cc_last_4 is None
    if not self.resized:
      if self.submissionphoto_set.filter(valid=False).exists():
        return 'The guest uploaded an invalid image file'
      return 'The photos haven\'t been resized yet.'
    if self.was_checked():
      return 'This submission was checked.'
    if no_last_4 and cc_photo_required(channel):
      return (
          'Channel {} requires a cc photo either because we assume cc risk or '
          'we take the security deposit. But in order to ask if the cc is '
          'correct we need a valid payment or security deposit so we can get '
          'the last 4 digits and know we\'re validating a valid cc.').format(
              self.reservation.channel)

  def id_photo(self):
    return self._photo(ID)

  def id_back_photo(self):
    return self._photo(BACK_OF_ID)

  def cc_photo(self):
    return self._photo(CC)

  def id_photo_url(self):
    return self._photo_url(ID)

  def id_back_url(self):
    return self._photo_url(BACK_OF_ID)

  def cc_photo_url(self):
    return self._photo_url(CC)

  def _photo_url(self, photo_type):
    photo = self._photo(photo_type)
    if photo:
      return photo.url()

  def _photo(self, photo_type):
    return self.submissionphoto_set.filter(photo_type=photo_type).first()
