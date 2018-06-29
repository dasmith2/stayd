from datetime import timedelta
import os
from random import choices
import string

from django.conf import settings
from django.db import models
from django.shortcuts import reverse
from django.utils.timezone import now
from PIL import Image

from id_verify.s3 import S3
from reservations.models import Reservation


class SubmissionManager(models.Manager):
  def resize(self):
    for submission in Submission.objects.filter(
        resized=False, reservation__isnull=False):
      submission.resize()

  def remove_unnecessary_images(
      self, s3=S3(), verbose=False, use_settings=settings):
    if not use_settings.CAN_DELETE_FROM_S3:
      raise Exception(
          'This server can\'t remove_unnecessary_images because it doesn\'t '
          'know what reservations are valid and therefore what images are '
          'necessary.')
    for (file_name, last_modified) in s3.list():
      submission = self.filter(photo_file_name=file_name).first()
      if submission:
        explain = submission.explain_why_no_need_for_photo()
        if explain:
          if verbose:
            print('Deleting {} because {}'.format(file_name, explain))
          submission.photo_file_name = None
          submission.save()
          s3.delete(file_name)
      elif last_modified < now() - timedelta(days=1):
        if verbose:
          print((
              'Deleting {} because no submission is associated '
              'with it and it\'s over a day old.').format(file_name))
        s3.delete(file_name)

  def get_destination_file_name(self, file_type):
    """ This is where an id photo will get stored at first on S3. """
    if file_type == 'image/jpeg':
      suffix = 'jpg'
    else:
      raise Exception(
          'Not sure what to do with file_type {}'.format(file_type))
    random_str = ''.join(choices(string.ascii_uppercase + string.digits, k=7))
    return 'random{}.{}'.format(random_str, suffix)


class Submission(models.Model):
  """ This class represents a single submission of the id verification
  form. The photo is passed directly to our bucket on Amazon's S3 via
  Javascript because Django is a single threaded web framework. That means a
  file upload blocks the thread until it's done, so it's a bad idea to pass all
  the bytes of a big ol' user submitted image through the app itself, because
  that would block all incoming calls.

  There are 3 possible states. 1. The user just uploaded a photo. It's on S3,
  resized=False. 2. The compressor went through, renamed, and resized this
  photo. Now resized=True. 3. We deleted the photo because they're a huge
  security liability. Now resized is irrelevant and photo_file_name is blank.
  """
  photo_file_name = models.CharField(max_length=300, help_text=(
      'The file name of this photo in Amazon S3.'), null=True, blank=True,
      db_index=True)
  resized = models.BooleanField(default=False, help_text=(
      'Users will be uploading huge photos, I\'m sure. The '
      'id_verify.compressor goes through and shrinks them.'))
  email = models.CharField(max_length=100)
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  reservation = models.OneToOneField(
      Reservation, on_delete=models.CASCADE, null=True, help_text=(
          'This can be null because sometimes we might get a submission '
          'before janky Guesty sends us a webhook and we need to go back '
          'through and match them up.'))

  objects = SubmissionManager()

  def photo_url(self):
    return reverse('view_image', kwargs={'file_name': self.photo_file_name})

  def explain_why_no_need_for_photo(self):
    if self.reservation:
      if self.reservation.we_assume_credit_card_risk():
        expires_at = self.reservation.check_out + timedelta(days=93)
        if expires_at < now():
          return 'The guest can no longer charge back the credit card.'
      else:
        expires_at = self.reservation.check_out + timedelta(days=5)
        if expires_at < now():
          return 'We would have noticed any damage by now.'
    else:
      expires_at = self.created_at + timedelta(days=2)
      if expires_at < now():
        return 'No matching reservation after 2 days'
    return ''

  def resize(
      self, verbose=False, s3=S3(), image_opener=Image.open, use_os=os,
      use_open=open):
    """ This is a whole thing, and should run only in the background. """
    if not self.photo_file_name:
      raise Exception('This photo was deleted and can\'t be recovered.')
    if not self.reservation:
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
    new_name = '{}.jpg'.format(self.reservation.channel_reservation_id)
    if use_os.path.exists(new_name):
      use_os.remove(new_name)

    # I don't use the handy with as because I didn't bother to figure out
    # how to mock that whole thing in tests.
    file_handle = use_open(new_name, 'wb')
    image.save(file_handle, format='JPEG', quality=100)
    file_handle.close()

    s3.upload(new_name)
    use_os.remove(self.photo_file_name)
    use_os.remove(new_name)

    self.resized = True
    old_name = self.photo_file_name
    if verbose:
      print('Replacing {} with {}'.format(old_name, new_name))
    self.photo_file_name = new_name
    self.save()

    s3.delete(old_name)
