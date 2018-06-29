from collections import namedtuple
from datetime import timedelta
from unittest.mock import Mock, call

from django.test import TestCase
from django.utils.timezone import now

from id_verify.models import Submission
from id_verify.s3 import S3
from reservations.tests import get_test_reservation
from util.timezone import parse_dt
from util.channels import AIRBNB, BOOKINGCOM


def get_test_submission(create, **kwargs):
  reservation = get_test_reservation(create, **kwargs)

  submission = Submission(
      photo_file_name=kwargs.get('photo_file_name', 'whatever.jpg'),
      resized=kwargs.get('resized', False),
      email=kwargs.get('email', 'the_queen@gmail.com'),
      reservation=kwargs.get('reservation', reservation))

  if create:
    submission.save()
    if 'created_at' in kwargs:
      Submission.objects.filter(pk=submission.pk).update(
          created_at=parse_dt(kwargs['created_at']))
  elif 'created_at' in kwargs:
    raise Exception(
        'Due to django peculiarities, created_at can only be set to anything '
        'other than the default after it\'s been created, so you can only '
        'specify the created_at arg if create=True.')
  return submission


class SubmissionManagerTests(TestCase):
  def test_remove_unnecessary_images(self):
    use_settings = namedtuple(
        'settings', 'CAN_DELETE_FROM_S3')(CAN_DELETE_FROM_S3=True)
    mock_s3 = Mock(spec=S3)
    old = now() - timedelta(days=10)
    mock_s3.list.return_value = [
        ('no_submission_recent.jpg', now()),
        ('no_submission_old.jpg', old),
        ('no_reservation_recent.jpg', now()),
        ('no_reservation_old.jpg', old),
        ('reservation_recent.jpg', old),
        ('reservation_old.jpg', old)]

    get_test_submission(
        True, photo_file_name='no_reservation_recent.jpg', reservation=None)
    get_test_submission(
        True, photo_file_name='no_reservation_old.jpg', reservation=None,
        created_at='2017-01-01')
    get_test_submission(
        True, photo_file_name='reservation_recent.jpg', check_out=now())
    get_test_submission(
        True, photo_file_name='reservation_old.jpg',
        check_out=now() - timedelta(days=180))

    Submission.objects.remove_unnecessary_images(
        s3=mock_s3, use_settings=use_settings)

    expected_calls = [
        call('no_submission_old.jpg'), call('no_reservation_old.jpg'),
        call('reservation_old.jpg')]
    self.assertEqual(expected_calls, mock_s3.delete.call_args_list)

  def test_get_destination_file_name(self):
    name = Submission.objects.get_destination_file_name('image/jpeg')
    self.assertTrue(name.find('.jpg') > 0)


class SubmissionTests(TestCase):
  def test_explain_why_no_need_for_photo(self):
    book_old = get_test_submission(
        True, channel=AIRBNB, check_out=now() - timedelta(days=100))
    air_medium = get_test_submission(
        True, channel=AIRBNB, check_out=now() - timedelta(days=30))
    book_medium = get_test_submission(
        True, channel=BOOKINGCOM, check_out=now() - timedelta(days=30))
    air_new = get_test_submission(
        True, channel=AIRBNB, check_out=now())
    self.assertTrue(book_old.explain_why_no_need_for_photo())
    self.assertTrue(air_medium.explain_why_no_need_for_photo())
    self.assertEqual('', book_medium.explain_why_no_need_for_photo())
    self.assertEqual('', air_new.explain_why_no_need_for_photo())
    # The bit about no reservation is covered by test_remove_unnecessary_images

  def test_resize(self):
    sub = get_test_submission(
        True, photo_file_name='blargh.jpg', channel_reservation_id='HITHERE')
    mock_s3 = Mock(spec=S3)
    mock_image = Mock()
    mock_image.width = 1600
    mock_image.height = 3200
    mock_image.resize = Mock(return_value=mock_image)
    image_opener = Mock(return_value=mock_image)
    use_os = Mock()
    use_os.path = Mock()
    use_os.path.exists = Mock(return_value=False)
    use_os.remove = Mock()
    file_handle = Mock()
    file_handle.close = Mock()
    use_open = Mock(return_value=file_handle)
    sub.resize(
        s3=mock_s3, image_opener=image_opener, use_os=use_os,
        use_open=use_open)

    # Download the existing photo.
    self.assertEqual(
        mock_s3.download.call_args_list, [call('blargh.jpg')])
    # Open it.
    self.assertEqual(
        image_opener.call_args_list, [call('blargh.jpg')])
    # Resize it.
    self.assertEqual(
        mock_image.resize.call_args_list, [call((400, 800))])
    # Write it.
    self.assertEqual(
        use_open.call_args_list, [call('HITHERE.jpg', 'wb')])
    self.assertEqual(
        mock_image.save.call_args_list,
        [call(file_handle, format='JPEG', quality=100)])
    self.assertEqual(
        file_handle.close.call_args_list, [call()])
    # Upload it.
    self.assertEqual(
        mock_s3.upload.call_args_list, [call('HITHERE.jpg')])
    # Clean up.
    self.assertEqual(
        use_os.remove.call_args_list, [
            call('blargh.jpg'),
            call('HITHERE.jpg')])
    self.assertEqual(
        mock_s3.delete.call_args_list, [call('blargh.jpg')])
    # The database reflects the changes.
    sub.refresh_from_db()
    self.assertEqual(sub.photo_file_name, 'HITHERE.jpg')
    self.assertTrue(sub.resized)
