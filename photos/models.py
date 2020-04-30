""" Heroku machines don't stick around for long. So photo uploads have to go to
some kind of cloud storage. This... complicates things. We serve the user a
page such as the ID Verification page. That page contains Javascript and such
which allows the user to upload their photo directly to an Amazon S3 web cloud
storage bucket. THAT'S important because Django is a single threaded web
framework, and meanwhile phone companies are in a pissing contest for who can
make the biggest image files. So if the bytes of those photos had to come
through keys web, all web requests would have to wait for the upload to
complete.

Anyway in order to upload a photo, keys has to "sign" the metadata of the
upload. That happens server side since that requires access to api keys and
such. So requests to "sign" photo uploads are how we know all the photos that
got uploaded by users.  I mean, you can also call an api on the bucket to list
the contents, but that will start to break down if the bucket grows
monotonically with time. I believe that API call taps out after a thousand
photos.

OK, so the user uploaded a photo to S3. Then the html page will probably put
the resulting file name in a form somewhere. Eventually the user clicks some
kind of submit button, and when we get that POST, we finally know WHY the user
uploaded that photo, and we create objects that reference the uploaded file.

I have 1 central Photos table so that it's relatively straightforward to ask
the question, "Is anybody actually using this photo?" Whatever new feature you
need photos for, you should make a new model that inherits from this Photo
object, which you'll notice, is NOT abstract.

Photos have to describe when they can be thrown out. This keeps cost and
clutter down. I also keep cost and clutter down by resizing all photos. """
from abc import abstractmethod
from datetime import timedelta
import os

from django.conf import settings
from django.templatetags.static import static
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from PIL import Image

from commands.models import background_command
from photos.s3 import SignedPhoto, S3, photo_url
from util.background import background
from util.timezone import now


@background_command
def clean_up_never_used(nnow=None, s3=None):
  """ I find out about every photo that users upload because the server has to
  sign them. But WHY they're being used doesn't become clear until somebody
  creates a Photo object, and then the child class explains everything. So
  whatever photos exist without a Photo object are photos that got uploaded,
  but we never found out why. So just delete them. This is quite common. People
  might change their minds and upload a different photo, or they may just never
  submit the form that says why they uploaded that photo. """
  nnow = nnow or now()
  # It may take a moment for the background thread to catch up and use a photo,
  # or it may take the user a while to submit the form that says how to use the
  # file they just uploaded. So give it a day for the reason for the upload to
  # show up, and if it doesn't, chuck the upload.
  for signed in SignedPhoto.objects.filter(
      created_at__lte=nnow - timedelta(days=1)).order_by('pk'):
    if not signed_photo_is_used(signed):
      signed.delete_file(s3=s3)
    signed.delete()


def signed_photo_is_used(signed):
  maybe_used = Photo.objects.filter(
      file_name=signed.file_name).select_related(
          *PHOTO_SELECT_RELATED).first()
  if maybe_used:
    maybe_used_sensitive = (
        maybe_used.get_child_class_instance().sensitive())
    if maybe_used_sensitive == signed.sensitive:
      return True
  return False


PHOTO_SELECT_RELATED = [
    'submissionphoto', 'examplephoto', 'confirmationphoto', 'ticketphoto']


@background_command
def clean_up_no_longer_needed(nnow=None, s3=None):
  """ Photos have to describe when they can be thrown out. """
  nnow = nnow or now()
  # Sometimes a single empty file name slips into the database. There's a
  # unique constraint, so only 1 empty file_name is allowed haha Anyway
  # obviously you can't delete a file with no name.
  for photo in Photo.objects.filter(
      ~Q(file_name=''), keep_until__lt=nnow).select_related(
          *PHOTO_SELECT_RELATED):
    photo = photo.get_child_class_instance()
    if photo.explain_why_no_need_for_photo():
      photo.delete(s3=s3)
    else:
      photo.calc_and_set_keep(nnow=nnow)
      if photo.keep_forever or photo.keep_until >= nnow:
        photo.save()
      else:
        raise Exception(
            'Theres no reason to keep {} but calc_and_set_keep set '
            'keep_until to {} which is in the past'.format(
                photo, photo.keep_until))


@background_command
def list_unaccounted_images(
    sensitive, also_delete=False, also_print_urls=False, s3=None):
  """ Actually list the contents of the directory and compare it with the Photo
  and SignedPhoto classes. If you specify also_delete, you'll remove anything
  that we don't recognize from S3. Wow is this function dangerous. Especially
  in production, list the files first and double check a few to make sure you
  actually want to delete them. """
  s3 = s3 or S3(sensitive)
  actual_files = set()
  for file_name, modified_at in s3.list():
    actual_files.add(file_name)
  known_files = set()
  for photo in Photo.objects.all():
    known_files.add(photo.file_name)
  for signed_photo in SignedPhoto.objects.all():
    known_files.add(signed_photo.file_name)
  unaccounted = actual_files - known_files
  if also_print_urls:
    for file_name in unaccounted:
      print(photo_url(file_name, sensitive))
  if also_delete:
    dev_bucket_names = ['dev-hihoward-public', 'dev-stayd-id-verification']
    if s3._s3_bucket not in dev_bucket_names and not settings.PROD:
      raise Exception(
          'It seems like youre trying to clean up images in a production S3 '
          'bucket that are unaccounted for in a non production database. But '
          'a non production database has no idea what images are in '
          'production. So this would completely empty an entire S3 bucket of '
          'production images, which is a terrible mistake.')
    for file_name in unaccounted:
      s3.delete(file_name)
  return unaccounted


@background_command
def resize_all(nnow=None, **kwargs):
  """ If all we ever get is a SignedPhoto, then the image will never be
  resized. """
  nnow = nnow or now()
  for photo in Photo.objects.filter(
      ~Q(file_name=''),  # Sometimes a single empty file name is in the db
      resized_at__isnull=True,
      created_at__gte=nnow - timedelta(days=7)).select_related(
          *PHOTO_SELECT_RELATED):
    photo.get_child_class_instance().resize(**kwargs)


@background
def _do_resize_background(photo_id, **kwargs):
  # kwargs so I can pass Mocked objects all the way to the resize function.
  if settings.TEST and 's3' not in kwargs:
    return
  Photo.objects.get(pk=photo_id).get_child_class_instance().resize(**kwargs)


class Photo(models.Model):
  file_name = models.CharField(max_length=200, db_index=True, unique=True)
  valid = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  resized_at = models.DateTimeField(null=True)

  keep_until = models.DateTimeField(db_index=True, null=True, help_text=(
      'Once keep_until is in the past, Ill ask to '
      'explain_why_no_need_for_photo, and chuck this photo where '
      'appropriate.'))
  keep_forever = models.BooleanField(help_text=(
      'For instance, canonical clean apartment photos that cleaners should '
      'aspire to replicate are permanent.'))

  @abstractmethod
  def explain_why_no_need_for_photo(self, nnow=None):
    """ Explain why it's ok to throw this photo out. If you want to keep this
    photo, return nothing. """
    raise NotImplementedError('explain_why_no_need_for_photo')

  @abstractmethod
  def calc_and_set_keep(self, nnow=None):
    """ When should we definitely keep this photo until? Put that value in
    keep_until, or set keep_forever, but don't save. """
    raise NotImplementedError('explain_why_no_need_for_photo')

  @abstractmethod
  def sensitive(self):
    """ Is this a sensitive photo such as a photo of a credit card? This
    determines which Amazon s3 bucket the photo gets stored in, and the method
    for serving up the photo. The bytes of sensitive photos have to go through
    keys, otherwise browsers can just pull the photos down directly from S3.
    """
    raise NotImplementedError('sensitive')

  def get_child_class_instance(self):
    if self.__class__ != Photo:
      return self
    try:
      return self.submissionphoto
    except Photo.submissionphoto.RelatedObjectDoesNotExist:
      pass
    try:
      return self.examplephoto
    except Photo.examplephoto.RelatedObjectDoesNotExist:
      pass
    try:
      return self.confirmationphoto
    except Photo.confirmationphoto.RelatedObjectDoesNotExist:
      pass
    try:
      return self.ticketphoto
    except Photo.ticketphoto.RelatedObjectDoesNotExist:
      pass
    try:
      return self.testphoto
    except Photo.testphoto.RelatedObjectDoesNotExist:
      pass
    raise Exception(self)

  def save(self, **kwargs):
    """ kwargs so I can pass in a mock s3 in tests """
    super().save()
    if not self.resized_at:
      _do_resize_background(self.pk, **kwargs)

  def url(self):
    if not self.valid:
      return static('invalid_image.png')
    return photo_url(
        self.file_name, self.get_child_class_instance().sensitive())

  def delete(self, s3=None):
    child_instance = self.get_child_class_instance()
    if not child_instance.explain_why_no_need_for_photo():
      raise Exception((
          'Why are you deleting a photo with no explanation for why '
          'we can delete it?'), child_instance)
    s3 = s3 or self._s3()
    s3.delete(self.file_name)
    super().delete()

  def clean(self):
    if int(bool(self.keep_until)) + int(bool(self.keep_forever)) != 1:
      raise ValidationError('Either keep_until or keep_forever')
    if not self.file_name:
      raise ValidationError('file_name must be a non empty string')
    return super().clean()

  def notify_bad_image(self, **kwargs):
    """ You can use this to start a conversation with whoever uploaded a bad
    image, or you can just leave the default behavior of not really doing
    anything. """
    pass

  def do_additional_resize_steps(
      self, input_file_name, output_file_name, **kwargs):
    """ You can override this function if you want to have additional steps as
    part of resizing. For instance, id verification blanks out credit card
    numbers. """
    pass

  def _s3(self):
    return S3(sensitive=self.get_child_class_instance().sensitive())

  def post_resize(self):
    pass

  def resize(
      self, verbose=False, image_opener=None, use_os=None, use_open=None,
      **kwargs):
    """ This is a whole thing, and should run only in the background. It tries
    to run right away, but it also runs every night at midnight to help catch
    problems, so there are races possible, such as both threads trying to
    delete the working images. """
    if self.resized_at:
      return True

    image_opener = image_opener or Image.open
    use_os = use_os or os
    use_open = use_open or open
    s3 = kwargs.get('s3', None) or self._s3()

    if self.__class__ == Photo:
      raise Exception('Call resize on the child class')
    if self.resized_at:
      return
    if not self.file_name:
      raise Exception('This photo was deleted and can\'t be recovered.')
    s3.download(self.file_name)

    try:
      image = image_opener(self.file_name)
    except OSError as ex:
      if ex.args[0].find('cannot identify image file') == 0:
        self.notify_bad_image(**kwargs)
        return False
      raise ex

    # Sometimes people will upload pngs. Sometimes they'll upload pngs but
    # replace the file extension with jpg. Whatever, people are dumb at image
    # file formats. In any case just make sure it doesn't have an alpha channel
    # so we can save it as a jpg, which is pretty much the sane format for a
    # photograph.
    try:
      image = image.convert('RGB')
    except OSError as ex:
      if ex.args[0].find('image file is truncated') == 0:
        self.notify_bad_image(**kwargs)
        return False
      raise ex

    (width, height) = (image.width, image.height)
    max_dimension = max((width, height))
    if max_dimension > self.max_width_or_height():
      ratio = self.max_width_or_height() / max_dimension
      image = image.resize((int(ratio * width), int(ratio * height)))

    if use_os.path.exists(self.file_name):
      use_os.remove(self.file_name)

    # I don't use the handy `with ... as` because I didn't bother to figure out
    # how to mock that whole thing in tests.
    file_handle = use_open(self.file_name, 'wb')
    image.save(file_handle, format='JPEG', quality=100)
    file_handle.close()

    self.do_additional_resize_steps(self.file_name, self.file_name, **kwargs)

    s3.upload(self.file_name)
    use_os.remove(self.file_name)

    self.resized_at = kwargs.get('nnow', now())
    self.save()

    self.post_resize()
    return True

  def max_width_or_height(self):
    return 800.0

  def __repr__(self):
    return '<{} {}: {}>'.format(
        self._meta.model_name, self.pk, self.file_name)

  class Meta:
    abstract = False  # This makes cleaning up unused photos fairly simple.


class TestPhoto(Photo):
  """ I need a child class to write tests against. """
  next_keep_until = models.DateTimeField(null=True)
  next_keep_forever = models.BooleanField(null=True)
  why_no_need_for_photo = models.CharField(
      max_length=200, default='', blank=True)
  is_sensitive = models.BooleanField(default=False)

  def explain_why_no_need_for_photo(self):
    return self.why_no_need_for_photo

  def calc_and_set_keep(self, nnow=None):
    self.keep_until = self.next_keep_until
    self.keep_forever = self.next_keep_forever

  def sensitive(self):
    return self.is_sensitive
