from unittest.mock import Mock, call

from photos.models import (
    TestPhoto, Photo, clean_up_never_used, clean_up_no_longer_needed,
    resize_all, signed_photo_is_used)
from photos.s3 import SignedPhoto, S3
from util.random_string import random_string
from util.tests import TestCase
from util.timezone import str_to_tz_dt


def get_test_photo(**kwargs):
  if 'sensitive' in kwargs:
    raise Exception(
        'TestPhotos have an is_sensitive field and a sensitive() function')
  test_photo = TestPhoto(
      next_keep_until=kwargs.get('next_keep_until', None),
      next_keep_forever=kwargs.get('next_keep_forever', None),
      why_no_need_for_photo=kwargs.get('why_no_need_for_photo', ''),
      is_sensitive=kwargs.get('is_sensitive', False))
  return set_photo_stuff(test_photo, **kwargs)


def set_photo_stuff(photo, **kwargs):
  photo.file_name = kwargs.get('file_name', random_string())
  photo.valid = kwargs.get('valid', True)
  photo.resized_at = kwargs.get('resized_at', None)
  photo.keep_until = kwargs.get('keep_until', None)
  photo.keep_forever = kwargs.get('keep_forever', not photo.keep_until)
  if 'created_at' in kwargs:
    Photo.objects.filter(pk=photo.pk).update(created_at=kwargs['created_at'])
    photo.refresh_from_db()
  photo.save()
  return photo


def get_test_signed_photo(**kwargs):
  if 'is_sensitive' in kwargs:
    raise Exception('SignedPhotos have a sensitive field')
  signed_photo = SignedPhoto.objects.create(
      file_name=kwargs.get('file_name', None),
      sensitive=kwargs.get('sensitive', False))
  if 'created_at' in kwargs:
    SignedPhoto.objects.filter(pk=signed_photo.pk).update(
        created_at=kwargs['created_at'])
    signed_photo.refresh_from_db()
  return signed_photo


class SignedPhotoIsUsedTests(TestCase):
  def setUp(self):
    super().setUp()
    get_test_photo(file_name='earballs.jpg', is_sensitive=False)

  def test_signed_photo_is_used(self):
    earballs = get_test_signed_photo(file_name='earballs.jpg', sensitive=False)
    self.assertTrue(signed_photo_is_used(earballs))

  def test_signed_photo_is_not_used(self):
    earballs = get_test_signed_photo(file_name='earballs.jpg', sensitive=True)
    self.assertFalse(signed_photo_is_used(earballs))


class CleanUpNeverUsedTests(TestCase):
  def test_clean_up_never_used(self):
    # Used
    get_test_signed_photo(
        file_name='verbs.jpg', sensitive=False,
        created_at=str_to_tz_dt('2018-12-24 12:00'))
    get_test_photo(
        file_name='verbs.jpg', keep_forever=True, is_sensitive=False)
    # Created too recently
    recent = get_test_signed_photo(
        file_name='participles.jpg', sensitive=False,
        created_at=str_to_tz_dt('2018-12-24 12:01'))
    # Coincidentally, there's a sensitive photo with the same name. But that
    # means it's in a totally different bucket, so this should get cleaned up.
    get_test_signed_photo(
        file_name='nouns.jpg', sensitive=True,
        created_at=str_to_tz_dt('2018-12-24 12:00'))
    get_test_photo(
        file_name='nouns.jpg', keep_forever=True, is_sensitive=False)
    # Standard abandoned upload. Clean it up.
    get_test_signed_photo(
        file_name='adjectives.jpg', sensitive=True,
        created_at=str_to_tz_dt('2018-12-24 12:00'))

    s3 = Mock(spec=S3)
    clean_up_never_used(nnow=str_to_tz_dt('2018-12-25 12:00'), s3=s3)
    self.assertEqual(
        [call('nouns.jpg'), call('adjectives.jpg')], s3.delete.call_args_list)
    self.assertEqual(set([recent]), set(list(SignedPhoto.objects.all())))


class CleanUpNoLongerNeededTests(TestCase):
  def test_had_earlier_remove_date_moved_to_later(self):
    photo = get_test_photo(
        file_name='ldnsldkf',
        keep_until=str_to_tz_dt('2018-12-25 12:00'),
        next_keep_until=str_to_tz_dt('2019-01-01 12:00'),
        next_keep_forever=False)
    clean_up_no_longer_needed(nnow=str_to_tz_dt('2018-12-26'))
    photo.refresh_from_db()
    self.assertEqual(str_to_tz_dt('2019-01-01 12:00'), photo.keep_until)

  def test_clean_up_no_longer_needed(self):
    # Don't bother checking. keep_until is in the future.
    get_test_photo(
        file_name='industrial', keep_until=str_to_tz_dt('2019-01-01'))
    # Keep forever.
    get_test_photo(file_name='size', keep_forever=True)
    # keep_until in the past, but there's no reason it's ok to delete and the
    # new keep_until is in the future.
    get_test_photo(
        file_name='autonomous',
        keep_until=str_to_tz_dt('2018-12-24'),
        next_keep_until=str_to_tz_dt('2019-01-01'),
        next_keep_forever=False)
    # Actually delete this one.
    deleted = get_test_photo(
        file_name='mowers',
        keep_until=str_to_tz_dt('2018-12-24'),
        why_no_need_for_photo='You actually could delete this')
    s3 = Mock(spec=S3)
    clean_up_no_longer_needed(nnow=str_to_tz_dt('2018-12-25 12:00'), s3=s3)
    self.assertEqual([call('mowers')], s3.delete.call_args_list)
    self.assertEqual(3, TestPhoto.objects.count())
    self.assertFalse(TestPhoto.objects.filter(pk=deleted.pk).exists())


class ResizeTests(TestCase):
  def setUp(self):
    super().setUp()
    self.photo = get_test_photo(file_name='humblebrag.jpg', keep_forever=True)
    self.assertIsNone(self.photo.resized_at)
    self.s3 = Mock(spec=S3)
    self.mock_image = Mock()
    self.mock_image.width = 1600
    self.mock_image.height = 3200
    self.mock_image.convert.return_value = self.mock_image
    self.mock_image.resize.return_value = self.mock_image
    self.image_opener = Mock(return_value=self.mock_image)
    self.use_os = Mock()
    self.use_os.path = Mock()
    self.use_os.path.exists.return_value = False
    self.use_os.remove = Mock()
    self.file_handle = Mock()
    self.file_handle.close = Mock()
    self.use_open = Mock(return_value=self.file_handle)

  def test_resize_base_class_raises_exception(self):
    try:
      Photo.objects.first().resize(s3=Mock())
    except Exception as ex:
      self.assertEqual('Call resize on the child class', ex.args[0])

  def test_backup_resize(self):
    resize_all(
        s3=self.s3, image_opener=self.image_opener, use_os=self.use_os,
        use_open=self.use_open)
    self.assert_resized()

  def test_resize(self):
    self.photo.resize(
        s3=self.s3, image_opener=self.image_opener, use_os=self.use_os,
        use_open=self.use_open)
    self.assert_resized()

  def assert_resized(self):
    # Download the existing photo.
    self.assertEqual(
        self.s3.download.call_args_list, [call('humblebrag.jpg')])
    # Open it.
    self.assertEqual(
        self.image_opener.call_args_list, [call('humblebrag.jpg')])
    # Make sure it's in RGB format so it can save as a jpg
    self.assertEqual(
        self.mock_image.convert.call_args_list, [call('RGB')])
    # Resize it.
    self.assertEqual(
        self.mock_image.resize.call_args_list, [call((400, 800))])
    # Write it.
    self.assertEqual(
        self.use_open.call_args_list, [call('humblebrag.jpg', 'wb')])
    self.assertEqual(
        self.mock_image.save.call_args_list,
        [call(self.file_handle, format='JPEG', quality=100)])
    self.assertEqual(
        self.file_handle.close.call_args_list, [call()])
    # Upload it, overwriting the original.
    self.assertEqual(
        self.s3.upload.call_args_list, [call('humblebrag.jpg')])
    # Clean up locally.
    self.assertEqual(
        [call('humblebrag.jpg')], self.use_os.remove.call_args_list)
    # The database reflects the changes.
    self.photo.refresh_from_db()
    self.assertEqual(self.photo.file_name, 'humblebrag.jpg')
    self.assertTrue(self.photo.resized_at)
