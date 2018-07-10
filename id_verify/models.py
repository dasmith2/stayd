from datetime import timedelta
import os

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.shortcuts import reverse
from django.utils.timezone import now
from PIL import Image

from errors.models import ErrorLogger
from guesty.models import GuestyReservation
from id_verify.s3 import S3
from reservations.models import Reservation
from util.channels import THEY_ASSUME_CC_RISK_CHANNELS


ID = 'ID'
CC = 'CC'
PHOTO_TYPE_CHOICES = (
    (ID, ID),
    (CC, CC))


class SubmissionManager(models.Manager):
  def check_these(self):
    last_4_is_not_null = Q(reservation__cc_last_4__isnull=False)
    they_assume_cc_risk = Q(
        reservation__listing__channel__in=THEY_ASSUME_CC_RISK_CHANNELS)
    return self.filter(
        last_4_is_not_null | they_assume_cc_risk,
        id_matches_reservation__isnull=True, resized=True,
        created_at__gt=now() - timedelta(days=30), reservation__isnull=False)

  def handle_post(self, post, api_getter=None):
    reservation = self.get_reservation_by_guest_name_or_alert(
        post['guest_name'])
    submission = self.create(
        guest_name=post['guest_name'],
        email=post['submit_email'],
        opt_in_email=post['opt_in_email'] == 'true',
        phone=post['submit_phone'],
        opt_in_texts=post['opt_in_texts'] == 'true',
        reservation=reservation)
    SubmissionPhoto.objects.create(
        submission=submission,
        photo_type=ID,
        photo_file_name=post['id_file_upload'])
    if 'cc_file_upload' in post:
      SubmissionPhoto.objects.create(
          submission=submission,
          photo_type=CC,
          photo_file_name=post['cc_file_upload'])
    # This is not great, making the user wait while we do two round trips
    # to guesty. But we can remove it once we start sending emails, which is
    # supposed to happen in the next month or so, so let's not over-engineer
    # this temporary solution.
    guesty_res = GuestyReservation.objects.filter(
        reservation=reservation).first()
    if guesty_res:
      custom_fields = guesty_res.get_custom_fields(api_getter=api_getter)
      custom_fields.set(
          settings.COMPLETE_ID_VERIFICATION_EMAIL_FIELD_ID, False)
      custom_fields.send_changes(api_getter)
    return submission

  def resize(self, verbose=False):
    for submission in self.filter(
        resized=False, reservation__isnull=False).select_related(
            'reservation'):
      submission.resize(verbose=verbose)

  def remove_unnecessary_images(
      self, s3=S3(), verbose=False, use_settings=settings):
    if not use_settings.CAN_DELETE_FROM_S3:
      raise Exception(
          'This server can\'t remove_unnecessary_images because it doesn\'t '
          'know what reservations are valid and therefore what images are '
          'necessary.')
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

  def get_reservation_by_guest_name(self, full_name):
    return self._get_reservations_by_guest_name(full_name).first()

  def get_reservation_by_guest_name_or_alert(
      self, full_name, logger=ErrorLogger()):
    reservations = self._get_reservations_by_guest_name(full_name)
    if reservations.count() == 1:
      # Whew!
      return reservations[0]
    elif reservations.count() > 1:
      reservation_ids = ','.join([str(res.pk) for res in reservations])
      message = (
          'Returning the first one, but you\'d better look into it.\n'
          'Reservation ids: {}').format(reservation_ids)
      logger.log_error(
          'Multiple reservations found for {}'.format(full_name), message)
      return reservations[0]
    elif reservations.count() == 0:
      logger.log_error(
          'No reservations found for {}'.format(full_name), 'Wah!')

  def _get_reservations_by_guest_name(self, full_name):
    return Reservation.objects.filter(
        guest__full_name=full_name, check_in__gt=now())


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
  guest_name = models.CharField(max_length=200, help_text=(
      'We collect this no matter what in case we can\'t automatically '
      'figure out what reservation this is for.'))
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
  reservation = models.OneToOneField(
      Reservation, on_delete=models.CASCADE, null=True, help_text=(
          'This can be null because sometimes we might get a submission '
          'before janky Guesty sends us a webhook and we need to go back '
          'through and match them up.'))
  id_matches_reservation = models.NullBooleanField(
      null=True, blank=True, help_text=(
          'Does the name on the ID match the name of the person who made '
          'the reservation? Required for all reservations.'))
  id_matches_cc = models.NullBooleanField(
      null=True, blank=True, help_text=(
          'Does the name on the ID match the name on the credit card? '
          'This only applies on reservations where we assume credit card risk '
          'like Booking.com'))
  cc_matches_reservation = models.NullBooleanField(
      null=True, blank=True, help_text=(
          'Do the last 4 digits of the cc and the type of cc match the card '
          'used to make the reservation? This only applies on reservations '
          'where we assume credit card risk like Booking.com'))
  checked_at = models.DateTimeField(null=True, blank=True)

  objects = SubmissionManager()

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
    return self.id_matches_reservation is not None

  def explain_why_not_check(self):
    if not self.reservation:
      return 'We don\'t know what reservation this submission is for yet.'
    channel = self.reservation.listing.channel
    no_last_4 = self.reservation.cc_last_4 is None
    if not self.resized:
      return 'The photos haven\'t been resized yet.'
    if self.was_checked():
      return 'This submission was checked.'
    if no_last_4 and channel not in THEY_ASSUME_CC_RISK_CHANNELS:
      return (
          'We assume the payment risk and no valid payment occurred yet, '
          'so it\'s not worth it to verify the cc yet because it might '
          'be declined and we have to review a totally different one.')

  def cc_photo_url(self):
    return self._photo_url(CC)

  def id_photo_url(self):
    return self._photo_url(ID)

  def _photo_url(self, photo_type):
    photo = SubmissionPhoto.objects.filter(
        submission=self, photo_type=photo_type).first()
    if photo:
      return photo.photo_url()


class SubmissionPhoto(models.Model):
  submission = models.ForeignKey(Submission, on_delete=models.CASCADE)
  photo_type = models.CharField(max_length=10, choices=PHOTO_TYPE_CHOICES)
  photo_file_name = models.CharField(max_length=200, db_index=True)

  def photo_url(self):
    return reverse('view_image', kwargs={'file_name': self.photo_file_name})

  def explain_why_no_need_for_photo(self):
    if self.submission.reservation:
      if self.submission.reservation.we_assume_credit_card_risk():
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
    new_name = '{}.jpg'.format(
        self.submission.reservation.channel_reservation_id)
    if use_os.path.exists(new_name):
      use_os.remove(new_name)

    # I don't use the handy `with ... as` because I didn't bother to figure out
    # how to mock that whole thing in tests.
    file_handle = use_open(new_name, 'wb')
    image.save(file_handle, format='JPEG', quality=100)
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
