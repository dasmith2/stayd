from datetime import timedelta
from unittest.mock import Mock, call

from django.conf import settings
from util.tests import TestCase
from django.utils.timezone import now

from errors.models import ErrorLogger
from front.models import Front
from guest_messages.models import SMS
from guest_messages.models_base import (
    LAST_NAME_ID_RES_DO_NOT_MATCH, FIRST_LAST_NAME_ID_CC_DO_NOT_MATCH,
    LAST_4_BRAND_CC_RES_DO_NOT_MATCH, NO_NAMES_MATCH,
    LAST_NAME_ID_RES_LAST_4_BRAND_CC_DO_NOT_MATCH,
    FULL_NAME_CC_ID_LAST_4_BRAND_CC_DO_NOT_MATCH, EVERYTHING_WRONG,
    RESEND_ID_VERIFICATION_LINK)
from guest_messages.tests import get_test_template
from guesty.api_getter import GuestyAPIGetter
from guesty.models import GuestyReservation
from id_verify.models import (
    Submission, SubmissionPhoto, ID, SubmissionResizer,
    do_resend_id_verification, post_submission_steps)
from id_verify.s3 import S3
from reservations.tests import get_test_reservation
from util.channels import AIRBNB, BOOKINGCOM
from util.email import EmailSender
from util.timezone import parse_dt


def get_test_submission(create, **kwargs):
  reservation = get_test_reservation(create, **kwargs)

  submission = Submission(
      email=kwargs.get('email', 'the_queen@gmail.com'),
      opt_in_email=kwargs.get('opt_in_email', True),
      phone=kwargs.get('phone', ''),
      opt_in_texts=kwargs.get('opt_in_texts', True),
      resized=kwargs.get('resized', False),
      reservation=kwargs.get('reservation', reservation),
      id_matches_res=kwargs.get('id_matches_res', None),
      cc_matches_id=kwargs.get('cc_matches_id', None),
      cc_matches_payment=kwargs.get('cc_matches_payment', None))

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


def get_checkable_submission(create, **kwargs):
  kwargs['resized'] = True
  kwargs['check_in'] = now() + timedelta(days=2)
  submission = get_test_submission(create, **kwargs)
  get_test_submission_photo(create, submission=submission, photo_type=ID)
  return submission


def get_test_submission_photo(create, **kwargs):
  submission = get_test_submission(create, **kwargs)

  submission_photo = SubmissionPhoto(
      submission=kwargs.get('submission', submission),
      photo_type=kwargs.get('photo_type', ID),
      photo_file_name=kwargs.get('photo_file_name', 'whatever.jpg'))

  if create:
    submission_photo.save()
  return submission_photo


class ResendTest(TestCase):
  def test_do_resend_id_verification(self):
    reservation = get_test_reservation(True)
    get_test_template(True, guesty_custom_field_id=RESEND_ID_VERIFICATION_LINK)
    front = Front(testing=True)
    sent = do_resend_id_verification(reservation.pk, front=front)
    self.assertEqual(
        'Success!', sent['result'])


class SubmissionTests(TestCase):
  def test_get_reservation_from_verify_id_query(self):
    res = get_test_reservation(
        True, phone='1(917)608-4623', full_name='Ed Viesturs',
        check_in=now() + timedelta(days=1))
    self.assertIsNone(
        Submission.objects.get_reservation_from_verify_id_query({}))
    self.assertEqual(
        res,
        Submission.objects.get_reservation_from_verify_id_query({
            'phone': '19176084623'}))
    self.assertEqual(
        res,
        Submission.objects.get_reservation_from_verify_id_query({
            'name': 'Ed Viesturs'}))

  def test_checkable_submissions(self):
    yes = get_checkable_submission(True)
    get_checkable_submission(True, status='not confirmed')
    self.assertEqual([yes], list(Submission.objects.checkable_submissions()))

  def test_get_template_id_by_problem(self):
    air = get_test_submission(False, channel=AIRBNB)
    air.id_matches_res = False
    air.cc_matches_id = False
    air.cc_matches_payment = False
    self.assertEqual(
        air._get_template_id_by_problem(), LAST_NAME_ID_RES_DO_NOT_MATCH)
    air.id_matches_res = True
    self.assertIsNone(air._get_template_id_by_problem())

    book = get_test_submission(False, channel=BOOKINGCOM)

    def set_book(id_matches_res, cc_matches_id, cc_matches_payment):
      book.id_matches_res = id_matches_res
      book.cc_matches_id = cc_matches_id
      book.cc_matches_payment = cc_matches_payment

    set_book(False, False, False)
    self.assertEqual(book._get_template_id_by_problem(), EVERYTHING_WRONG)
    set_book(False, False, True)
    self.assertEqual(book._get_template_id_by_problem(), NO_NAMES_MATCH)
    set_book(False, True, False)
    self.assertEqual(
        book._get_template_id_by_problem(),
        LAST_NAME_ID_RES_LAST_4_BRAND_CC_DO_NOT_MATCH)
    set_book(False, True, True)
    self.assertEqual(
        book._get_template_id_by_problem(), LAST_NAME_ID_RES_DO_NOT_MATCH)
    set_book(True, False, False)
    self.assertEqual(
        book._get_template_id_by_problem(),
        FULL_NAME_CC_ID_LAST_4_BRAND_CC_DO_NOT_MATCH)
    set_book(True, False, True)
    self.assertEqual(
        book._get_template_id_by_problem(), FIRST_LAST_NAME_ID_CC_DO_NOT_MATCH)
    set_book(True, True, False)
    self.assertEqual(
        book._get_template_id_by_problem(), LAST_4_BRAND_CC_RES_DO_NOT_MATCH)

  def test_check_these(self):
    last_4_not_null_booking = get_test_submission(
        True, cc_last_4='1234', cc_brand='Visa', channel=BOOKINGCOM,
        resized=True)
    self.assertFalse(last_4_not_null_booking.explain_why_not_check())

    last_4_null_airbnb = get_test_submission(True, resized=True)
    self.assertFalse(last_4_null_airbnb.explain_why_not_check())

    last_4_null_booking = get_test_submission(
        True, channel=BOOKINGCOM, resized=True)
    self.assertTrue(last_4_null_booking.explain_why_not_check())

    no_reservation = get_test_submission(True, reservation=None, resized=True)
    self.assertTrue(no_reservation.explain_why_not_check())

    not_resized = get_test_submission(True)
    self.assertTrue(not_resized.explain_why_not_check())

    checked_already = get_test_submission(
        True, resized=True, id_matches_res=False)
    self.assertTrue(checked_already.explain_why_not_check())

    expect_check_these = set(
        [last_4_not_null_booking.pk, last_4_null_airbnb.pk])
    checkable = Submission.objects.checkable_submissions()
    got_check_these = set(sub.pk for sub in checkable)
    self.assertEqual(expect_check_these, got_check_these)

  def test_remove_unnecessary_images(self):
    mock_s3 = Mock(spec=S3)
    old = now() - timedelta(days=10)
    mock_s3.list.return_value = [
        ('no_submission_recent.jpg', now()),
        ('no_submission_old.jpg', old),
        ('no_reservation_recent.jpg', now()),
        ('no_reservation_old.jpg', old),
        ('reservation_recent.jpg', old),
        ('reservation_old.jpg', old)]

    get_test_submission_photo(
        True, photo_file_name='no_reservation_recent.jpg', reservation=None)
    get_test_submission_photo(
        True, photo_file_name='no_reservation_old.jpg', reservation=None,
        created_at='2017-01-01')
    get_test_submission_photo(
        True, photo_file_name='reservation_recent.jpg', check_out=now())
    get_test_submission_photo(
        True, photo_file_name='reservation_old.jpg',
        check_out=now() - timedelta(days=180))

    Submission.objects.remove_unnecessary_images(s3=mock_s3)

    expected_calls = [
        call('no_submission_old.jpg'), call('no_reservation_old.jpg'),
        call('reservation_old.jpg')]
    self.assertEqual(expected_calls, mock_s3.delete.call_args_list)

  def test_handle_submission_post(self):
    reservation = get_test_reservation(
        True, full_name='The Queen', check_in=now() + timedelta(days=2))
    GuestyReservation.objects.create(
        reservation=reservation, guesty_id='blahblahbluesheep')
    post = {
        'query': {'name': 'The Queen'},
        'reservation_id': reservation.pk,
        'submit_email': 'the_queen@gmail.com',
        'opt_in_email': 'false',
        'opt_in_texts': 'true',
        'submit_phone': '555-666-7789',
        'id_file_upload': 'hey.jpg'}

    api_getter = Mock(spec=GuestyAPIGetter)
    api_getter.get_one.return_value = {'customFields': []}
    email_sender = Mock(spec=EmailSender)
    submission_resizer = Mock(spec=SubmissionResizer)
    submission = Submission.objects.handle_submission_post(
        post, api_getter, email_sender, submission_resizer)
    # Right now this runs every hour as part of
    # id_verify/management/commands/resize_and_clean_up_id_images.py
    # But I want to get on-demand background threads working so I can
    # kick this off immediately post-submission.
    post_submission_steps(
        submission_pk=None, api_getter=api_getter,
        email_sender=email_sender, submission_resizer=submission_resizer)
    # The post submit step are designed to run on a background thread so
    # there's a step where we load by id from the DB and update that one.
    submission.refresh_from_db()

    self.assertEqual(1, len(email_sender.send_mail.call_args_list))
    self.assertEqual(1, len(submission_resizer.resize.call_args_list))
    expected_fields = [{
        'fieldId': settings.EMAIL_PROVIDED_FIELD_ID,
        'value': 'the_queen@gmail.com'}, {
        'fieldId': settings.PHONE_PROVIDED_FIELD_ID,
        'value': '555-666-7789'}, {
        'fieldId': settings.COMPLETE_ID_VERIFICATION_EMAIL_FIELD_ID,
        'value': False}]

    self.assertEqual(
        api_getter.put.call_args_list,
        [call(
            'reservations/blahblahbluesheep',
            {"customFields": expected_fields})])

    self.assertEqual(submission.query, '{\'name\': \'The Queen\'}')
    self.assertEqual(submission.email, 'the_queen@gmail.com')
    self.assertEqual(submission.opt_in_email, False)
    self.assertEqual(submission.phone, '555-666-7789')
    self.assertEqual(submission.opt_in_texts, True)
    self.assertEqual(submission.reservation, reservation)
    self.assertIsNotNone(submission.post_submission_steps_at)

    photos = SubmissionPhoto.objects.filter(submission=submission)
    self.assertEqual(1, photos.count())
    self.assertEqual('hey.jpg', photos.first().photo_file_name)

  def test_handle_id_verify_list_post_ok(self):
    reservation = get_test_reservation(
        True, check_in=now() + timedelta(days=2), channel=BOOKINGCOM)
    GuestyReservation.objects.create(
        reservation=reservation, guesty_id='booboogreencow')

    ok = get_test_submission(True, channel=BOOKINGCOM, reservation=reservation)
    self.assertIsNone(ok.checked_at)
    self.assertIsNone(ok.id_matches_res)
    self.assertIsNone(ok.cc_matches_id)
    self.assertIsNone(ok.cc_matches_payment)

    post = {}
    post['submission_{}'.format(ok.pk)] = 'yep'
    post['{}_id_matches_res'.format(ok.pk)] = 'yes'
    post['{}_cc_matches_id'.format(ok.pk)] = 'yes'
    post['{}_cc_matches_payment'.format(ok.pk)] = 'yes'

    api_getter = Mock(spec=GuestyAPIGetter)
    api_getter.get_one.return_value = {'customFields': []}
    front = Mock(spec=Front)
    Submission.objects.handle_id_verify_list_post(post, front, api_getter)

    ok.refresh_from_db()
    self.assertIsNotNone(ok.checked_at)
    self.assertTrue(ok.id_matches_res)
    self.assertTrue(ok.cc_matches_id)
    self.assertTrue(ok.cc_matches_payment)

    fields = [{
        'fieldId': settings.ID_VERIFIED_FIELD_ID,
        'value': True}]
    self.assertEqual(
        0, SMS.objects.filter(reservation=reservation).count())
    self.assertEqual(
        api_getter.put.call_args_list,
        [call('reservations/booboogreencow', {"customFields": fields})])

  def test_handle_id_verify_list_post_not_ok(self):
    reservation = get_test_reservation(
        True, check_in=now() + timedelta(days=2), channel=BOOKINGCOM)
    GuestyReservation.objects.create(
        reservation=reservation, guesty_id='blarghblarghtealhippo')
    get_test_template(
        True, guesty_custom_field_id=EVERYTHING_WRONG)

    not_ok = get_test_submission(
        True, channel=BOOKINGCOM, reservation=reservation)

    post = {}
    post['submission_{}'.format(not_ok.pk)] = 'yep'
    post['{}_id_matches_res'.format(not_ok.pk)] = 'no'
    post['{}_cc_matches_id'.format(not_ok.pk)] = 'no'
    post['{}_cc_matches_payment'.format(not_ok.pk)] = 'no'

    api_getter = Mock(spec=GuestyAPIGetter)
    api_getter.get_one.return_value = {'customFields': []}
    front = Mock(spec=Front)
    Submission.objects.handle_id_verify_list_post(post, front, api_getter)

    not_ok.refresh_from_db()
    self.assertIsNotNone(not_ok.checked_at)
    self.assertFalse(not_ok.id_matches_res)
    self.assertFalse(not_ok.cc_matches_id)
    self.assertFalse(not_ok.cc_matches_payment)

    self.assertEqual(api_getter.put.call_args_list, [])
    message = SMS.objects.get(reservation=reservation)
    self.assertEqual(
        message.guesty_custom_field_id, EVERYTHING_WRONG)
    self.assertFalse(message.explain_why_do_not_send())

  def test_get_reservation_by_id_or_alert(self):
    logger = Mock(spec=ErrorLogger)
    reservation = get_test_reservation(
        True, full_name='The Queen of my apartment',
        check_in=now() + timedelta(days=2))
    found = Submission.objects.get_reservation_by_id_or_alert(
        reservation.pk, 'err msg', logger=logger)
    self.assertEqual(reservation, found)
    self.assertEqual([], logger.log_error.call_args_list)
    not_found = Submission.objects.get_reservation_by_id_or_alert(
        1000000, 'err msg 2', logger=logger)
    self.assertIsNone(not_found)
    self.assertEqual(1, len(logger.log_error.call_args_list))

  def test_resize(self):
    photo = get_test_submission_photo(
        True, photo_file_name='blargh.jpg', channel_reservation_id='HITHERE')
    self.assertFalse(photo.submission.resized)
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
    photo.submission.resize(
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
    new_file_name = 'HITHERE_{}_ID.jpg'.format(photo.submission.pk)
    self.assertEqual(
        use_open.call_args_list, [call(new_file_name, 'wb')])
    self.assertEqual(
        mock_image.save.call_args_list,
        [call(file_handle, format='JPEG', quality=100)])
    self.assertEqual(
        file_handle.close.call_args_list, [call()])
    # Upload it.
    self.assertEqual(
        mock_s3.upload.call_args_list, [call(new_file_name)])
    # Clean up locally and remotely.
    self.assertEqual(
        use_os.remove.call_args_list, [
            call('blargh.jpg'),
            call(new_file_name)])
    self.assertEqual(
        mock_s3.delete.call_args_list, [call('blargh.jpg')])
    # The database reflects the changes.
    photo.refresh_from_db()
    self.assertEqual(photo.photo_file_name, new_file_name)
    self.assertTrue(photo.submission.resized)


class SubmissionPhotoTests(TestCase):
  def test_explain_why_no_need_for_photo(self):
    book_old = get_test_submission_photo(
        True, channel=AIRBNB, check_out=now() - timedelta(days=100))
    air_medium = get_test_submission_photo(
        True, channel=AIRBNB, check_out=now() - timedelta(days=30))
    book_medium = get_test_submission_photo(
        True, channel=BOOKINGCOM, check_out=now() - timedelta(days=30))
    air_new = get_test_submission_photo(
        True, channel=AIRBNB, check_out=now())
    self.assertTrue(book_old.explain_why_no_need_for_photo())
    self.assertTrue(air_medium.explain_why_no_need_for_photo())
    self.assertEqual('', book_medium.explain_why_no_need_for_photo())
    self.assertEqual('', air_new.explain_why_no_need_for_photo())
    # The bit about no reservation is covered by test_remove_unnecessary_images
