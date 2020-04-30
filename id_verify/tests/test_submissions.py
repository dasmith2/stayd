from collections import namedtuple
from datetime import timedelta
import os
from unittest.mock import Mock, call

from django.shortcuts import reverse
from google.cloud.vision import ImageAnnotatorClient

from errors.models import ErrorLogger
from front.models import Front
from guest_messages.models.message import (
    LAST_NAME_ID_RES_DO_NOT_MATCH, FIRST_LAST_NAME_ID_CC_DO_NOT_MATCH,
    LAST_4_BRAND_CC_RES_DO_NOT_MATCH, NO_NAMES_MATCH,
    LAST_NAME_ID_RES_LAST_4_BRAND_CC_DO_NOT_MATCH,
    FULL_NAME_CC_ID_LAST_4_BRAND_CC_DO_NOT_MATCH, CC_ID_EVERYTHING_WRONG,
    INVALID_IMAGE_UPLOAD, GUEST_UPLOADED_US_ID_FRONT_ONLY,
    GUEST_UPLOADED_NON_US_ID)
from id_verify.cc_blanker import CCBlanker
from id_verify.models import (
    Submission, SubmissionPhoto, unprocessed_post_submission_steps, ID,
    BACK_OF_ID, CC, US_ID_FRONT_ONLY, NON_US_ID)
from id_verify.models.submission_list import get_submission_list_table
from id_verify.verify_id_ui import (
    handle_opt_out_bgcheck, handle_submission_post)
from photos.s3 import S3
from reservations.syncer import GenericSyncer
from reservations.tests import get_test_reservation
from util.channels import AIRBNB, BOOKINGCOM, ONLY_APARTMENTS
from util.email import EmailSender
from util.random_string import random_string
from util.tests import TestCase
from util.timezone import parse_dt, now, str_to_tz_dt
from util import twilio


def get_test_submission(**kwargs):
  reservation = kwargs.get('reservation', None)
  if not reservation and 'reservation' not in kwargs:
    reservation = get_test_reservation(**kwargs)

  submission = Submission(
      query=kwargs.get('query', '{\'phone\': [\'1234567890\']}'),
      email=kwargs.get('email', 'the_queen@gmail.com'),
      opt_in_email=kwargs.get('opt_in_email', True),
      phone=kwargs.get('phone', ''),
      opt_in_texts=kwargs.get('opt_in_texts', True),
      resized=kwargs.get('resized', False),
      reservation=reservation,
      id_matches_res=kwargs.get('id_matches_res', None),
      cc_matches_id=kwargs.get('cc_matches_id', None),
      cc_matches_payment=kwargs.get('cc_matches_payment', None),
      has_negative_reviews=kwargs.get('has_negative_reviews', None),
      positive_reviews=kwargs.get('positive_reviews', None),
      booking_for_themself=kwargs.get('booking_for_themself', None),
      explained_trip=kwargs.get('explained_trip', None),
      lives_nearby=kwargs.get('lives_nearby', None),
      checked_at=kwargs.get('checked_at', None),
      checked_by=kwargs.get('checked_by', None),
      risk_score=kwargs.get('risk_score', None),
      post_submission_steps_at=kwargs.get('post_submission_steps_at', None),
      birthday=kwargs.get('birthday', None),
      legal_name=kwargs.get('legal_name', ''),
      id_type=kwargs.get('id_type', ''),
      opt_out_of_bgcheck=kwargs.get('opt_out_of_bgcheck', False))

  default_has_is_voip = Mock(spec=twilio)
  default_has_is_voip.is_voip.return_value = False
  has_is_voip = kwargs.get('has_is_voip', default_has_is_voip)
  default_syncer = Mock(spec=GenericSyncer)
  syncer = kwargs.get('syncer', default_syncer)
  submission.save(has_is_voip=has_is_voip, syncer=syncer)

  if 'created_at' in kwargs:
    Submission.objects.filter(pk=submission.pk).update(
        created_at=parse_dt(kwargs['created_at']))
    submission.refresh_from_db()
  return submission


def get_checkable_submission(**kwargs):
  kwargs['resized'] = True
  kwargs['check_in'] = now() + timedelta(days=2)
  kwargs['check_out'] = now() + timedelta(days=4)
  if 'guesty_id' not in kwargs:
    kwargs['guesty_id'] = random_string()
  submission = get_test_submission(**kwargs)
  id_file_name = kwargs.get('id_file_name', '{}.jpg'.format(random_string()))
  get_test_submission_photo(
      submission=submission, photo_type=ID, file_name=id_file_name, **kwargs)
  if 'id_back_file_name' in kwargs:
    get_test_submission_photo(
        submission=submission, photo_type=BACK_OF_ID,
        file_name=kwargs['id_back_file_name'], **kwargs)
  if 'cc_file_name' in kwargs:
    get_test_submission_photo(
        submission=submission, photo_type=CC,
        file_name=kwargs['cc_file_name'], **kwargs)
  return submission


def get_test_submission_photo(**kwargs):
  submission = kwargs.get('submission', None)
  if not submission:
    submission = get_test_submission(**kwargs)
  photo_type = kwargs.get('photo_type', ID)

  if submission.submissionphoto_set.filter(photo_type=photo_type).exists():
    raise Exception(
        'This submission already has a {}, possibly because you called '
        'get_checkable_submission?'.format(photo_type))

  submission_photo = SubmissionPhoto(
      submission=submission,
      photo_type=photo_type,
      file_name=kwargs.get('file_name', '{}.jpg'.format(random_string())),
      resized_at=kwargs.get('resized_at', None))
  submission_photo.calc_and_set_keep()
  submission_photo.save()
  return submission_photo


class CCBlankerTests(TestCase):
  def test_blank_cc(self):
    # Sheesh
    Symbol = namedtuple('Symbol', 'text')
    Word = namedtuple('Word', 'symbols bounding_box')
    Vertex = namedtuple('Vertex', 'x y')
    Box = namedtuple('Box', 'vertices')

    def make_word(word_str, vertices_ints):
      symbols = [Symbol(c) for c in word_str]
      vertices = [Vertex(x, y) for (x, y) in vertices_ints]
      return Word(symbols, Box(vertices))

    words = [
        make_word('3775', [(323, 413), (419, 413), (419, 487), (323, 487)]),
        make_word('3775', [(450, 413), (547, 413), (547, 487), (450, 487)]),
        make_word('3775', [(585, 413), (682, 413), (682, 487), (585, 487)]),
        make_word('3775', [(720, 413), (817, 413), (817, 487), (720, 487)])]
    response = namedtuple('Response', 'full_text_annotation')(
        namedtuple('Document', 'pages')([
            namedtuple('Page', 'blocks')([
                namedtuple('Block', 'paragraphs')([
                    namedtuple('Paragraph', 'words')(words)])])]))

    image_annotator_client = Mock(spec=ImageAnnotatorClient)
    image_annotator_client.document_text_detection.return_value = response

    if os.path.exists('realistic_fake_cc_blanked_in_unit_test.jpg'):
      os.remove('realistic_fake_cc_blanked_in_unit_test.jpg')

    CCBlanker().blank_cc(
        'static/realistic_fake_cc.jpg',
        'realistic_fake_cc_blanked_in_unit_test.jpg',
        image_annotator_client=image_annotator_client)

    with open('static/realistic_fake_cc_blanked.jpg', 'rb') as expected_file:
      expected_bytes = expected_file.read()
    with open('realistic_fake_cc_blanked_in_unit_test.jpg', 'rb') as actual_f:
      actual_bytes = actual_f.read()
    self.assertEqual(expected_bytes, actual_bytes)
    os.remove('realistic_fake_cc_blanked_in_unit_test.jpg')


class SubmissionTests(TestCase):
  def test_unprocessed_post_submission_steps(self):
    get_test_submission(  # Done already.
        created_at=str_to_tz_dt('2018-12-25 12:00'),
        post_submission_steps_at=str_to_tz_dt('2018-12-26 12:00'))
    get_test_submission(  # No reservation.
        created_at=str_to_tz_dt('2018-12-25 12:00'), reservation=None)
    get_test_submission(  # Too old
        created_at=str_to_tz_dt('2018-05-25'))
    yes = get_test_submission(
        created_at=str_to_tz_dt('2018-12-25 12:00'))
    self.assertEqual([yes], list(
        unprocessed_post_submission_steps(
            nnow=str_to_tz_dt('2018-12-27 12:00'))))

  def test_match_reservations_to_reservationless_submissions(self):
    submission = get_test_submission(
        reservation=None, query=str({'phone': ['6665554444']}),
        resized=False)
    reservation = get_test_reservation(
        phone='+1(666)555-4444', check_out=now() + timedelta(days=1))

    syncer = Mock(spec=GenericSyncer)
    email_sender = Mock(spec=EmailSender)

    Submission.objects.match_reservations_to_reservationless_submissions(
        syncer=syncer, email_sender=email_sender)

    submission.refresh_from_db()
    self.assertEqual(submission.reservation, reservation)

  def test_checkable_submissions(self):
    yes = get_checkable_submission(guesty_id='LearnedThatOneTheHardWay')
    get_checkable_submission(
        status='not confirmed', guesty_id='ThisIsMyLifeNow')
    self.assertEqual([yes], list(Submission.objects.checkable_submissions()))

  def test_get_triggering_event_by_problem(self):
    air = get_test_submission(channel=AIRBNB)
    air.id_matches_res = False
    air.cc_matches_id = False
    air.cc_matches_payment = False
    self.assertEqual(
        air._get_triggering_event_by_problem(), LAST_NAME_ID_RES_DO_NOT_MATCH)
    air.id_matches_res = True
    self.assertIsNone(air._get_triggering_event_by_problem())

    sub = get_test_submission(channel=BOOKINGCOM)

    def set_book(id_matches_res, cc_matches_id, cc_matches_payment):
      sub.id_matches_res = id_matches_res
      sub.cc_matches_id = cc_matches_id
      sub.cc_matches_payment = cc_matches_payment

    set_book(False, False, False)
    self.assertEqual(
        sub._get_triggering_event_by_problem(), CC_ID_EVERYTHING_WRONG)
    set_book(False, False, True)
    self.assertEqual(sub._get_triggering_event_by_problem(), NO_NAMES_MATCH)
    set_book(False, True, False)
    self.assertEqual(
        sub._get_triggering_event_by_problem(),
        LAST_NAME_ID_RES_LAST_4_BRAND_CC_DO_NOT_MATCH)
    set_book(False, True, True)
    self.assertEqual(
        sub._get_triggering_event_by_problem(), LAST_NAME_ID_RES_DO_NOT_MATCH)
    set_book(True, False, False)
    self.assertEqual(
        sub._get_triggering_event_by_problem(),
        FULL_NAME_CC_ID_LAST_4_BRAND_CC_DO_NOT_MATCH)
    set_book(True, False, True)
    self.assertEqual(
        sub._get_triggering_event_by_problem(),
        FIRST_LAST_NAME_ID_CC_DO_NOT_MATCH)
    set_book(True, True, False)
    self.assertEqual(
        sub._get_triggering_event_by_problem(),
        LAST_4_BRAND_CC_RES_DO_NOT_MATCH)
    set_book(True, True, True)
    sub.id_type = US_ID_FRONT_ONLY
    self.assertEqual(
        sub._get_triggering_event_by_problem(),
        GUEST_UPLOADED_US_ID_FRONT_ONLY)
    sub.id_type = NON_US_ID
    self.assertEqual(
        sub._get_triggering_event_by_problem(),
        GUEST_UPLOADED_NON_US_ID)

  def test_check_these(self):
    last_4_not_null_booking = get_test_submission(
        cc_last_4='1234', cc_brand='Visa', channel=BOOKINGCOM,
        resized=True)
    self.assertFalse(last_4_not_null_booking.explain_why_not_check())

    last_4_null_airbnb = get_test_submission(resized=True)
    self.assertFalse(last_4_null_airbnb.explain_why_not_check())

    last_4_null_booking = get_test_submission(
        channel=BOOKINGCOM, resized=True)
    self.assertTrue(last_4_null_booking.explain_why_not_check())

    no_reservation = get_test_submission(reservation=None, resized=True)
    self.assertTrue(no_reservation.explain_why_not_check())

    not_resized = get_test_submission()
    self.assertTrue(not_resized.explain_why_not_check())

    checked_already = get_test_submission(
        resized=True, id_matches_res=False)
    self.assertTrue(checked_already.explain_why_not_check())

    last_4_null_only_apartments = get_test_submission(
        cc_last_4=None, cc_brand=None, channel=ONLY_APARTMENTS,
        resized=True)
    self.assertTrue(last_4_null_only_apartments.explain_why_not_check())
    last_4_not_null_only_apartments = get_test_submission(
        cc_last_4='1234', cc_brand='VISA', channel=ONLY_APARTMENTS,
        resized=True)
    self.assertFalse(last_4_not_null_only_apartments.explain_why_not_check())

    expect_check_these = set([
        last_4_not_null_booking.pk, last_4_null_airbnb.pk,
        last_4_not_null_only_apartments.pk])
    checkable = Submission.objects.checkable_submissions()
    got_check_these = set(sub.pk for sub in checkable)
    self.assertEqual(expect_check_these, got_check_these)

  def test_resize_bad_image(self):
    def image_opener(file_name):
      raise OSError("cannot identify image file 'random3ASUUB7_id.jpg'")
    s3 = Mock(spec=S3)
    front = Mock(spec=Front)
    # Still haven't worked out how to de-confuse guest messages. Guest messages
    # wants to know about things so it can, say, check if the background check
    # is successful before sending the checkin instructions. But elsewhere we
    # want to call guest messages to send messages and such.
    from guest_messages.tests import get_test_smstemplate
    get_test_smstemplate(
        triggering_event=INVALID_IMAGE_UPLOAD,
        guesty_custom_field_id=None, message='Image! Bad!')

    photo = get_test_submission_photo(
        file_name='blargh.jpg', channel_id='HITHERE', phone='111-222-3434')
    photo.save(s3=s3, front=front, image_opener=image_opener)

    photo.refresh_from_db()
    self.assertFalse(photo.submission.resized)
    self.assertFalse(photo.valid)
    self.assertEqual(1, len(front.send_sms.call_args_list))
    self.assertEqual(
        [call('111-222-3434', 'Image! Bad!')], front.send_sms.call_args_list)

  def test_resize(self):
    photo = get_test_submission_photo(
        file_name='blargh.jpg', channel_id='HITHERE', photo_type=CC)
    self.assertFalse(photo.submission.resized)
    s3 = Mock(spec=S3)
    mock_image = Mock()
    mock_image.width = 1600
    mock_image.height = 3200
    mock_image.convert.return_value = mock_image
    mock_image.resize.return_value = mock_image
    image_opener = Mock(return_value=mock_image)
    use_os = Mock()
    use_os.path = Mock()
    use_os.path.exists.return_value = False
    use_os.remove = Mock()
    file_handle = Mock()
    file_handle.close = Mock()
    use_open = Mock(return_value=file_handle)
    blanker = Mock(spec=CCBlanker)
    photo.save(
        s3=s3, image_opener=image_opener, use_os=use_os,
        use_open=use_open, blanker=blanker)

    # Download the existing photo.
    self.assertEqual(
        s3.download.call_args_list, [call('blargh.jpg')])
    # Open it.
    self.assertEqual(
        image_opener.call_args_list, [call('blargh.jpg')])
    # Make sure it's in RGB format so it can save as a jpg
    self.assertEqual(
        mock_image.convert.call_args_list, [call('RGB')])
    # Resize it.
    self.assertEqual(
        mock_image.resize.call_args_list, [call((400, 800))])
    # Write it.
    self.assertEqual(
        use_open.call_args_list, [call('blargh.jpg', 'wb')])
    self.assertEqual(
        mock_image.save.call_args_list,
        [call(file_handle, format='JPEG', quality=100)])
    self.assertEqual(
        file_handle.close.call_args_list, [call()])
    # blank out credit card numbers
    self.assertEqual(
        [call('blargh.jpg', 'blargh.jpg')], blanker.blank_cc.call_args_list)
    # Upload it, overwriting the original.
    self.assertEqual(
        s3.upload.call_args_list, [call('blargh.jpg')])
    # Clean up locally.
    self.assertEqual([call('blargh.jpg')], use_os.remove.call_args_list)
    # The database reflects the changes.
    photo.refresh_from_db()
    self.assertEqual(photo.file_name, 'blargh.jpg')
    self.assertTrue(photo.resized_at)
    self.assertTrue(photo.submission.resized)


class CleanUpSubmissionPhotoTests(TestCase):
  def setUp(self):
    super().setUp()
    self.nnow = str_to_tz_dt('2018-12-25 12:00')
    self.book_old = get_test_submission_photo(
        channel=BOOKINGCOM, check_out=self.nnow - timedelta(days=100))
    self.air_medium = get_test_submission_photo(
        channel=AIRBNB, check_out=self.nnow - timedelta(days=30))
    self.book_medium = get_test_submission_photo(
        channel=BOOKINGCOM, check_out=self.nnow - timedelta(days=30))
    self.air_new = get_test_submission_photo(
        channel=AIRBNB, check_out=self.nnow)

    self.no_reservation_old = get_test_submission_photo(
        channel=AIRBNB, submission=get_test_submission(
            created_at=self.nnow - timedelta(hours=49), reservation=None))
    self.no_reservation_new = get_test_submission_photo(
        channel=AIRBNB, submission=get_test_submission(
            created_at=self.nnow - timedelta(hours=47), reservation=None))

  def test_explain_why_no_need_for_photo(self):
    self.assertTrue(
        self.book_old.explain_why_no_need_for_photo(nnow=self.nnow))
    self.assertTrue(
        self.air_medium.explain_why_no_need_for_photo(nnow=self.nnow))
    self.assertEqual(
        '', self.book_medium.explain_why_no_need_for_photo(nnow=self.nnow))
    self.assertEqual(
        '', self.air_new.explain_why_no_need_for_photo(nnow=self.nnow))
    self.assertTrue(
        self.no_reservation_old.explain_why_no_need_for_photo(nnow=self.nnow))
    self.assertEqual(
        '',
        self.no_reservation_new.explain_why_no_need_for_photo(nnow=self.nnow))

  def test_calc_and_set_keep(self):
    self.assertEqual(
        self.nnow - timedelta(days=100) + timedelta(days=93),
        self.book_old.keep_until)
    self.assertFalse(self.book_old.keep_forever)
    self.assertEqual(
        self.nnow - timedelta(days=30) + timedelta(days=5),
        self.air_medium.keep_until)
    self.assertEqual(
        self.nnow - timedelta(hours=49) + timedelta(hours=48),
        self.no_reservation_old.keep_until)


class VerifyIDUITests(TestCase):
  def test_handle_opt_out_bgcheck(self):
    reservation = get_test_reservation()
    post = {
        'bgcheck_opt_out': 'true',
        'reservation_id': reservation.pk}
    handle_opt_out_bgcheck(post)
    self.assertEqual(1, Submission.objects.count())
    Submission.objects.get(reservation=reservation, opt_out_of_bgcheck=True)

  def test_handle_submission_post(self):
    reservation = get_test_reservation(
        full_name='The Queen', check_in=now() + timedelta(days=2),
        check_out=now() + timedelta(days=4))
    post = {
        'query': {'name': 'The Queen'},
        'unique_form_id': 'asdf1234',
        'reservation_id': reservation.pk,
        'submit_email': 'the_queen@gmail.com ',  # Spaces should be trimmed.
        'opt_in_email': 'false',
        'opt_in_texts': 'true',
        'submit_phone': '555-666-7789 ',
        'id_file_upload': 'hey.jpg'}

    syncer = Mock(spec=GenericSyncer)
    email_sender = Mock(spec=EmailSender)
    logger = Mock(spec=ErrorLogger)
    # Pretend the user resubmits.
    for i in range(2):
      submission = handle_submission_post(
          post, email_sender, syncer=syncer, logger=logger)
    self.assertEqual(1, Submission.objects.count())
    logger.log_error.assert_not_called
    # The post submit step are designed to run on a background thread so
    # there's a step where we load by id from the DB and update that one.
    submission.refresh_from_db()

    self.assertEqual(1, len(email_sender.send_mail.call_args_list))
    self.assertEqual(
        syncer.set_phone_email.call_args_list,
        [call(reservation, '555-666-7789', 'the_queen@gmail.com')])

    self.assertEqual(submission.query, '{\'name\': \'The Queen\'}')
    self.assertEqual(submission.email, 'the_queen@gmail.com')
    self.assertEqual(submission.opt_in_email, False)
    self.assertEqual(submission.phone, '555-666-7789')
    self.assertEqual(submission.opt_in_texts, True)
    self.assertEqual(submission.reservation, reservation)
    self.assertIsNotNone(submission.post_submission_steps_at)

    photos = submission.submissionphoto_set.all()
    self.assertEqual(1, photos.count())
    self.assertEqual('hey.jpg', photos.first().file_name)

    get_submission_list_table(reservation, True)

  def test_verify_id(self):
    reservation = get_test_reservation(
        full_name='The Queen of England', first_name='The Queen',
        check_in=now() + timedelta(days=2),
        check_out=now() + timedelta(days=3), channel=AIRBNB)
    self.assert_get_contains(
        reservation.verify_id_url_no_server(),
        'The Queen, thanks for booking with Howard through Airbnb.')

  def test_verify_id_mobile(self):
    self.mobile_client.get(reverse('verify_id'))
