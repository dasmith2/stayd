import ast
from datetime import timedelta
import os
import re
from rq import Queue

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.shortcuts import reverse
from django.utils.timezone import now
from PIL import Image

from errors.models import ErrorLogger
from front.models import Front
from guest_messages.models.models import SMS, SMSTemplate
from guest_messages.models.models_base import (
    LAST_NAME_ID_RES_DO_NOT_MATCH, FIRST_LAST_NAME_ID_CC_DO_NOT_MATCH,
    LAST_4_BRAND_CC_RES_DO_NOT_MATCH, NO_NAMES_MATCH,
    LAST_NAME_ID_RES_LAST_4_BRAND_CC_DO_NOT_MATCH,
    FULL_NAME_CC_ID_LAST_4_BRAND_CC_DO_NOT_MATCH, CC_ID_EVERYTHING_WRONG,
    RESEND_ID_VERIFICATION_LINK)
from guests.models import GuestPhoneNumber
from id_verify.s3 import S3
from reservations.models import Reservation, CONFIRMED
from util.background import background
from util.channels import THEY_ASSUME_CC_RISK_CHANNELS
from util.email import EmailSender
from util.image import pil_format_from_file_name
from worker import conn


q = Queue(connection=conn)


ID = 'ID'
CC = 'CC'
PHOTO_TYPE_CHOICES = (
    (ID, ID),
    (CC, CC))


def do_resend_id_verification(reservation_id, front=Front()):
  reservation = Reservation.objects.get(pk=reservation_id)
  message = SMSTemplate.objects.triggered_message_for_reservation(
      RESEND_ID_VERIFICATION_LINK, reservation)
  SMS.objects.send(message_pk=message.pk, front=front)
  return {'result': 'Success!'}


class SubmissionResizer(object):
  """ Whole point of this thing is having something to mock in tests. """
  def resize(self, submission):
    submission.resize()


class SubmissionManager(models.Manager):
  def match_reservations_to_reservationless_submissions(
      self, syncer=None, email_sender=EmailSender(),
      submission_resizer=SubmissionResizer(), verbose=False):
    for submission in Submission.objects.filter(
        created_at__gt=now() - timedelta(days=3), reservation__isnull=True):
      useful_dict = {}
      # query string dicts do values as lists.
      for key, value in ast.literal_eval(submission.query).items():
        if isinstance(value, list):
          value = value[0]
        useful_dict[key] = value
      reservation = self.get_reservation_from_verify_id_query(useful_dict)
      if reservation:
        if verbose:
          print(
              'Matching submission {} up to reservation {} based on {}'.format(
                  submission.pk, reservation.pk, submission.query))
        submission.reservation = reservation
        submission.save()
        post_submission_steps(
            submission_pk=submission.pk, syncer=syncer,
            email_sender=email_sender, submission_resizer=submission_resizer)
      elif verbose:
        print('Unable to find a match for query string {}'.format(
            submission.query))

  def checkable_submissions(self, escalated=None):
    last_4_is_not_null = Q(reservation__cc_last_4__isnull=False)
    they_assume_cc_risk = Q(
        reservation__channel__in=THEY_ASSUME_CC_RISK_CHANNELS)
    checkable = self.filter(
        last_4_is_not_null | they_assume_cc_risk,
        id_matches_res__isnull=True, resized=True,
        created_at__gt=now() - timedelta(days=30), reservation__isnull=False,
        reservation__status=CONFIRMED, reservation__id_verified=False)
    if escalated is True or escalated is False:  # i.e. not None
      checkable = checkable.filter(escalated=escalated)
    return checkable

  def get_url_to_create_a_checkable_submission(self):
    """ This is really just for development when you want to create a
    submission that will appear in the submissions list. """
    reservation = Reservation.objects.filter(
        Q(channel__in=THEY_ASSUME_CC_RISK_CHANNELS) | Q(
            cc_last_4__isnull=False),
        id_verified=False, check_out__gt=now()).first()
    if reservation:
      return reservation.verify_id_url()
    else:
      print(
          'No reservation in the database will do. Maybe set '
          'id_verified=False on a bunch or sync some.')

  def handle_submission_post(
      self, post, email_sender, submission_resizer, syncer=None,
      logger=ErrorLogger()):
    unique_form_id = post.get('unique_form_id', '')
    email = post.get('submit_email', '').strip()
    phone = post.get('submit_phone', '').strip()
    if unique_form_id:
      submission = Submission.objects.filter(
          unique_form_id=unique_form_id).first()
      if submission:
        submission.email = email
        submission.opt_in_email = post['opt_in_email'] == 'true'
        submission.phone = phone
        submission.opt_in_texts = post['opt_in_texts'] == 'true'
        submission.save()
        return submission
    reservation = None
    if post['reservation_id']:
      reservation = Reservation.objects.filter(
          pk=post['reservation_id']).first()
    submission = self.create(
        query=post['query'],
        unique_form_id=unique_form_id,
        email=email,
        opt_in_email=post['opt_in_email'] == 'true',
        phone=phone,
        opt_in_texts=post['opt_in_texts'] == 'true',
        reservation=reservation)
    id_photo = SubmissionPhoto.objects.create(
        submission=submission,
        photo_type=ID,
        photo_file_name=post['id_file_upload'])
    if 'cc_file_upload' in post:
      SubmissionPhoto.objects.create(
          submission=submission,
          photo_type=CC,
          photo_file_name=post['cc_file_upload'])
    if reservation:
      post_submission_steps(
          submission_pk=submission.pk, syncer=syncer,
          email_sender=email_sender, submission_resizer=submission_resizer)
    else:
      alert_message = (
          'Query string {}\nSubmission pk {}\nid photo {}{}').format(
              post['query'], submission.pk, settings.THIS_SERVERS_BASE_URL,
              id_photo.photo_url())
      logger.log_error(
          'No reservations found for submission', alert_message,
          always_new_error=True)
    return submission

  def handle_id_verify_list_post(self, post, front, syncer=None):
    for key in post.keys():
      found_id = re.compile(r'submission_(\d+)').match(key)
      if found_id:
        submission_id = int(found_id.groups()[0])

        def _boolean_helper(key_suffix):
          value_key = '{}{}'.format(submission_id, key_suffix)
          value = post.get(value_key, None)
          if value == 'yes':
            return True
          elif value == 'no':
            return False
          return None
        submission = Submission.objects.get(pk=submission_id)
        submission.id_matches_res = _boolean_helper('_id_matches_res')
        if submission.id_matches_res is None:
          continue
        if submission.reservation.we_assume_cc_risk():
          submission.cc_matches_id = _boolean_helper('_cc_matches_id')
          submission.cc_matches_payment = _boolean_helper(
              '_cc_matches_payment')
          if submission.cc_matches_id is None:
            continue
          if submission.cc_matches_payment is None:
            continue
        submission.save()
        post_check_id_steps(submission.pk, front, syncer=syncer)

  def handle_approve_escalated_submission_post(self, post, front, syncer=None):
    submission = Submission.objects.get(pk=post['submission_id'])
    submission.id_matches_res = True
    submission.cc_matches_id = True
    submission.cc_matches_payment = True
    submission.save()
    post_check_id_steps(submission.pk, front, syncer=syncer)

  def remove_unnecessary_images(self, s3=S3(), verbose=False):
    for (file_name, last_modified) in s3.list():
      photo = SubmissionPhoto.objects.filter(
          photo_file_name=file_name).select_related(
              'submission', 'submission__reservation').first()
      if photo:
        explain = photo.explain_why_no_need_for_photo()
        if explain:
          if verbose:
            print('Deleting {} because {}'.format(file_name, explain))
          s3.delete(file_name)
          photo.delete()
      elif last_modified < now() - timedelta(days=2):
        if verbose:
          print((
              'Deleting {} because no submission is associated '
              'with it and it\'s over two days old.').format(file_name))
        s3.delete(file_name)

  def get_reservation_from_verify_id_query(self, request_GET):
    """ See also verify_id_url_no_server in reservations.models.Reservation """
    name = request_GET.get('name', '')
    guest_first = request_GET.get('guest_first', '')
    phone = request_GET.get('phone', '')
    channel_id = request_GET.get('id', '')
    channel = request_GET.get('channel', '')
    reservations = Reservation.objects.filter(
        check_out__gt=now()).order_by('check_in')
    if name:
      reservations = reservations.filter(guest__full_name=name)
    if phone:
      guests = GuestPhoneNumber.objects.find_guests(phone)
      reservations = reservations.filter(guest__in=guests)
    if channel_id:
      reservations = reservations.filter(channel_reservation_id=channel_id)
    if guest_first:
      reservations = reservations.filter(guest__first_name=guest_first)
    if channel:
      reservations = reservations.filter(channel__iexact=channel)
    res_list = list(reservations)
    if len(res_list) == 1:
      # Whew!
      return res_list[0]
    if phone:
      # Well, if we got a phone number and there are multiple reservations,
      # that probably means it's for the same guest, so we can just return
      # one of the matches in that case.
      return reservations.first()


@background
def post_submission_steps(
    submission_pk=None, syncer=None,
    email_sender=EmailSender(), submission_resizer=SubmissionResizer(),
    verbose=False):
  if submission_pk:
    submissions = [Submission.objects.get(pk=submission_pk)]
  else:
    submissions = Submission.objects.filter(
        post_submission_steps_at__isnull=True, reservation__isnull=False)
  for submission in submissions:
    if verbose:
      print((
          'Settings custom fields, resizing, and notifying admins for '
          'submission {}').format(submission.pk))
    (syncer or submission.reservation.get_syncer()).set_phone_email(
        submission.reservation, submission.phone, submission.email)
    submission_resizer.resize(submission)
    subject = 'ID submitted for verification'
    url = reverse('submissions')
    if submission.reservation.has_payment_problem():
      subject = 'ID submitted, but there\'s a payment problem'
      url = reverse('payment_problems')
    email_sender.send_mail(
        subject,
        settings.VERIFY_ID_SERVER + url,
        'heroku@stayd.com', settings.ALERT_NEW_ID_SUBMISSION)
    submission.post_submission_steps_at = now()
    submission.save()


@background
def post_check_id_steps(submission_pk, front, syncer=None):
  submission = Submission.objects.get(pk=submission_pk)
  if submission.all_good():
    (syncer or submission.reservation.get_syncer()).set_id_verified(
        submission.reservation)
  else:
    submission.send_follow_up_message(front)
  submission.checked_at = now()
  submission.save()


class Submission(models.Model):
  """ This class represents a single submission of the id verification
  form. The photo is passed directly to our bucket on Amazon's S3 via
  Javascript because Django is a single threaded web framework. That means a
  file upload blocks the thread until it's done, so it's a bad idea to pass all
  the bytes of a big ol' user submitted image through the app itself, because
  that would block all incoming calls.

  There are 3 possible states. 1. The user just uploaded a photo. It's on S3,
  resized=False. 2. The compressor went through, renamed, and resized this
  submission's photos. Now resized=True. 3. We deleted the photos because
  they're a huge security liability. Now resized is irrelevant and the
  SubmissionPhotos are removed.
  """
  query = models.CharField(max_length=200, help_text=(
      'We collect this no matter what in case we can\'t automatically '
      'figure out what reservation this is for.'))
  unique_form_id = models.CharField(max_length=10, default='', help_text=(
      'This is just for detecting when the user hits refresh and submits '
      'the same form twice. Without this check, youll probably get a 404 '
      'as the second submission tries to resize its photos which have been '
      'resized in the meantime by the previous submission.'))
  email = models.CharField(max_length=100)
  opt_in_email = models.BooleanField(help_text=(
      'The guest checked a box saying its ok to contact them about discounted '
      'future stays via email. Note, they didnt agree to being contacted for '
      'any other reason, so resist the temptation!'))
  phone = models.CharField(max_length=100, blank=True, help_text=(
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

  def all_good(self):
    good = self.id_matches_res
    if self.reservation.we_assume_cc_risk():
      good = all([
          good,
          self.cc_matches_id,
          self.cc_matches_payment])
    return good

  def send_follow_up_message(self, front):
    triggering_event = self._get_triggering_event_by_problem()
    template = SMSTemplate.objects.get(triggering_event=triggering_event)
    message = template.create_new_message(self.reservation)
    SMS.objects.send(message_pk=message.pk, front=front)

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
    return None

  def resize(
      self, verbose=False, s3=S3(), image_opener=Image.open, use_os=os,
      use_open=open):
    for photo in SubmissionPhoto.objects.filter(
        submission=self).select_related('submission'):
      photo.resize(
          verbose=verbose, s3=s3, image_opener=image_opener, use_os=use_os,
          use_open=use_open)
    self.resized = True
    self.save()

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
      return 'The photos haven\'t been resized yet.'
    if self.was_checked():
      return 'This submission was checked.'
    if no_last_4 and channel not in THEY_ASSUME_CC_RISK_CHANNELS:
      return (
          'Either no valid payment occured yet, or the payment was taken '
          'in such a way that the cc details didn\'t show up in the API. We '
          'want a valid payment to occur first so we know we\'re verifying '
          'a valid CC.')

  def id_photo_url(self):
    return self._photo_url(ID)

  def cc_photo_url(self):
    return self._photo_url(CC)

  def _photo_url(self, photo_type):
    photo = SubmissionPhoto.objects.filter(
        submission=self, photo_type=photo_type).first()
    if photo:
      return photo.photo_url()


class SubmissionPhoto(models.Model):
  submission = models.ForeignKey(Submission, on_delete=models.CASCADE)
  photo_type = models.CharField(max_length=10, choices=PHOTO_TYPE_CHOICES)
  photo_file_name = models.CharField(max_length=200, db_index=True)

  def photo_file_suffix(self):
    return re.compile(r'\.\w+$').findall(self.photo_file_name)[0]

  def photo_url(self):
    return reverse('view_image', kwargs={'file_name': self.photo_file_name})

  def explain_why_no_need_for_photo(self):
    if self.submission.reservation:
      if self.submission.reservation.we_assume_cc_risk():
        expires_at = self.submission.reservation.check_out + timedelta(days=93)
        if expires_at < now():
          return 'The guest can no longer charge back the credit card.'
      else:
        expires_at = self.submission.reservation.check_out + timedelta(days=5)
        if expires_at < now():
          return 'We would have noticed any damage by now.'
    else:
      expires_at = self.submission.created_at + timedelta(days=2)
      if expires_at < now():
        return 'No matching reservation after 2 days'
    return ''

  def resized_name(self):
    """ Multiple submissions are allowed, so this has to take the submission
    pk into account otherwise new submissions overwrite the images for
    old submissions. """
    return '{}_{}_{}{}'.format(
        self.submission.reservation.channel_reservation_id, self.submission.pk,
        self.photo_type, self.photo_file_suffix())

  def resize(
      self, verbose=False, s3=S3(), image_opener=Image.open, use_os=os,
      use_open=open):
    """ This is a whole thing, and should run only in the background. """
    if not self.photo_file_name:
      raise Exception('This photo was deleted and can\'t be recovered.')
    if not self.submission.reservation:
      raise Exception(
          'This needs to have a reservation associated with it before I can '
          'resize and rename it because I use the confirmation id in the '
          'name.')
    s3.download(self.photo_file_name)

    image = image_opener(self.photo_file_name)
    (width, height) = (image.width, image.height)
    max_dimension = max((width, height))
    max_allowed = 800.0
    if max_dimension > max_allowed:
      ratio = max_allowed / max_dimension
      image = image.resize((int(ratio * width), int(ratio * height)))
    else:
      if verbose:
        print('It\'s small enough already. Not resizing.')
        return
    new_name = self.resized_name()
    if use_os.path.exists(new_name):
      use_os.remove(new_name)

    # I don't use the handy `with ... as` because I didn't bother to figure out
    # how to mock that whole thing in tests.
    file_handle = use_open(new_name, 'wb')
    image.save(
        file_handle, format=pil_format_from_file_name(new_name), quality=100)
    file_handle.close()

    s3.upload(new_name)
    use_os.remove(self.photo_file_name)
    use_os.remove(new_name)

    old_name = self.photo_file_name
    if verbose:
      print('Replacing {} with {}'.format(old_name, new_name))
    self.photo_file_name = new_name
    self.save()

    s3.delete(old_name)
