from datetime import date
from unittest.mock import Mock, call

from bgcheck.models.authenticating import (
    API, AuthenticatingCheck,
    PARSING_FAILED, UNKNOWN_STATE, COMPLETE)
from bgcheck.tests.test_background_check import (
    SubmissionTests, get_test_background_check)
from id_verify.models import BACK_OF_ID, US_ID_FRONT_AND_BACK
from id_verify.tests import get_test_submission, get_test_submission_photo
from photos.s3 import S3
from util.html_status_codes import NotOkError
from util.random_string import random_string
from util.tests import TestCase
from util.timezone import str_to_tz_dt


def get_test_authenticating_check(**kwargs):
  background_check = kwargs.get('background_check', None)
  if not background_check:
    background_check = get_test_background_check(**kwargs)
  return AuthenticatingCheck.objects.create(
      background_check=background_check,
      user_access_code=kwargs.get('user_access_code', random_string()),
      id_upload_result=kwargs.get('id_upload_result', ''),
      id_verified_result=kwargs.get('id_verified_result', None),
      has_criminal_record=kwargs.get('has_criminal_record', None))


class WorkflowTests(SubmissionTests):
  def setUp(self):
    super().setUp()
    self.api = Mock(spec=API)
    self.s3 = Mock(spec=S3)
    self.s3.utf8_encoded_image.side_effect = [
        'encoded_front_here', 'encoded_back_here']

  def test_create(self):
    self.api.create_user.return_value = {
        'userAccessCode': 'd348165c-d942-4eac-b219-3e12132ae7dc'}
    self.authenticating_check = AuthenticatingCheck.objects.create_new_check(
        self.check, api=self.api)
    expected = [call({
        'firstName': 'Davery',
        'lastName': 'Doo',
        'dob': '20-02-1957',
        'email': 'davery@doo.dave',
        'middleName': None, 'ssn': None, 'address': None,
        'city': None, 'state': None, 'zipCode': None})]
    got = self.api.create_user.call_args_list
    self.assertEqual(expected, got)
    self.assertEqual(
        self.authenticating_check, AuthenticatingCheck.objects.get(
            background_check=self.check,
            user_access_code='d348165c-d942-4eac-b219-3e12132ae7dc'))
    self.assertEqual('Created', self.authenticating_check.status())

  def switch_to_us_id(self):
    get_test_submission_photo(
        submission=self.submission, photo_type=BACK_OF_ID,
        file_name='davery_back_id.jpg')
    self.submission.id_type = US_ID_FRONT_AND_BACK
    self.submission.save()

  def test_confirm_consent(self):
    self.test_create()

    self.api.submit_user_consent.return_value = {'success': True}
    self.authenticating_check.do_next_step(api=self.api)
    # I refresh_from_db after any call to do_next_step just to make sure that
    # any changes were saved to the database.
    self.authenticating_check.refresh_from_db()
    self.assertEqual('Consent confirmed', self.authenticating_check.status())
    expected_data = {
        'userAccessCode': 'd348165c-d942-4eac-b219-3e12132ae7dc',
        'isReportChecked': 1,
        'isBackgroundDisclosureAccepted': 1,
        'fullName': 'Davery Doo'}
    self.assertEqual(
        [call(expected_data)], self.api.submit_user_consent.call_args_list)
    self.assertEqual('Consent confirmed', self.authenticating_check.status())

  def test_upload_passport(self):
    self.test_confirm_consent()

    self.api.upload_passport.return_value = {
        'success': True, 'attempt': '1'}
    self.authenticating_check.do_next_step(api=self.api, s3=self.s3)
    self.authenticating_check.refresh_from_db()
    self.assertEqual(
        [call('davery_id.jpg')], self.s3.utf8_encoded_image.call_args_list)
    expected_data = {
        'userAccessCode': 'd348165c-d942-4eac-b219-3e12132ae7dc',
        'idFront': 'encoded_front_here'}
    self.assertEqual(
        [call(expected_data)], self.api.upload_passport.call_args_list)
    self.assertEqual('ID upload attempted', self.authenticating_check.status())

  def test_upload_us_id(self):
    self.switch_to_us_id()
    self.test_confirm_consent()

    self.api.upload_id.return_value = {
        'success': True, 'attempt': '1'}
    self.authenticating_check.do_next_step(api=self.api, s3=self.s3)
    self.authenticating_check.refresh_from_db()
    self.assertEqual(
        [call('davery_id.jpg'), call('davery_back_id.jpg')],
        self.s3.utf8_encoded_image.call_args_list)
    expected_data = {
        'userAccessCode': 'd348165c-d942-4eac-b219-3e12132ae7dc',
        'idFront': 'encoded_front_here',
        'idBack': 'encoded_back_here',
        'country': 0}
    self.assertEqual(
        [call(expected_data)], self.api.upload_id.call_args_list)
    self.assertEqual('ID upload attempted', self.authenticating_check.status())

  def test_check_passport_upload(self):
    self.test_upload_passport()

    self.api.check_passport_upload.return_value = {
        'success': True,
        'result': 'complete',
        'description': 'blah blah blah'}
    self.authenticating_check.do_next_step(api=self.api)
    self.authenticating_check.refresh_from_db()
    expected_data = {
        'userAccessCode': 'd348165c-d942-4eac-b219-3e12132ae7dc'}
    self.assertEqual(
        [call(expected_data)], self.api.check_passport_upload.call_args_list)
    self.assertEqual(
        'ID upload successful', self.authenticating_check.status())

  def test_check_stuck_passport_upload(self):
    self.test_upload_passport()
    self.assertEqual('ID upload attempted', self.authenticating_check.status())
    self.authenticating_check.id_uploaded_on = str_to_tz_dt('2018-12-24 12:00')
    self.authenticating_check.save()
    self.api.check_passport_upload.return_value = {
        'success': False,
        'result': 'unknown_state',
        'numAttemptsLeft': 0,
        'description': (
            'This indicates that the call to checkUploadId has either been '
            'made too quickly after the image was uploaded or there has yet '
            'to be any image uploaded to the uploadId endpoint. If this '
            'result is received and an image has been sent to uploadId, try '
            'again after 20 seconds.')}

    bgcheck = self.authenticating_check.background_check
    self.authenticating_check.check_upload(
        api=self.api, nnow=str_to_tz_dt('2018-12-24 12:59'))
    self.assertFalse(bgcheck.backup_bgcheck_required)

    self.authenticating_check.check_upload(
        api=self.api, nnow=str_to_tz_dt('2018-12-24 13:00'))
    self.assertTrue(bgcheck.backup_bgcheck_required)
    self.assertEqual(
        'Check upload stuck', bgcheck.backup_bgcheck_required_because)

  def test_check_us_id_upload(self):
    self.test_upload_us_id()

    self.api.check_id_upload.return_value = {
        'success': True,
        'result': 'complete',
        'description': 'blah blah blah'}
    self.authenticating_check.do_next_step(api=self.api)
    self.authenticating_check.refresh_from_db()
    expected_data = {
        'userAccessCode': 'd348165c-d942-4eac-b219-3e12132ae7dc'}
    self.assertEqual(
        [call(expected_data)], self.api.check_id_upload.call_args_list)
    self.assertEqual(
        'ID upload successful', self.authenticating_check.status())

  def test_check_upload_id_unknown_state(self):
    self.test_upload_passport()

    self.api.check_passport_upload.return_value = {
        'success': False,
        'result': 'unknown_state',
        'description': 'blah blah blah'}
    self.authenticating_check.do_next_step(api=self.api)
    self.authenticating_check.refresh_from_db()

    self.assertEqual('ID upload attempted', self.authenticating_check.status())

  def test_check_upload_id_unknown_error(self):
    self.test_upload_passport()

    self.api.check_passport_upload.return_value = {
        'success': False,
        'result': 'unknown_error',
        'description': 'blah blah blah'}
    self.authenticating_check.do_next_step(api=self.api)
    self.authenticating_check.refresh_from_db()

    self.assertEqual('ID upload attempted', self.authenticating_check.status())

  def test_check_upload_id_cant_read_text(self):
    self.test_upload_passport()

    self.api.check_passport_upload.return_value = {
        'success': False,
        'result': PARSING_FAILED,
        # (sic)
        'description': 'Successful. This can be caused by poor quality photos'}
    self.api.get_test_result.return_value = {
        'backgroundCheck': {'hasCriminalRecord': None},
        'idVerification': {
            'status': 'FAILED',
            'description': 'The data on the ID could not be verified.'},
        'passportData': None,
        'scannedUser': {
            'DateOfBirth4': None,
            'NameFirst': None,
            'NameLast': None,
            'NameMiddle': None,
            'IsBarcodeRead': False,
            'IsIDVerified': False,
            'IsOcrRead': False}}
    self.authenticating_check.do_next_step(api=self.api)
    self.authenticating_check.refresh_from_db()

    self.assertEqual('ID parsing failed', self.authenticating_check.status())
    self.check.refresh_from_db()
    self.assertTrue(self.check.backup_bgcheck_required)
    self.assertEqual(
        'Couldnt read the text on the ID',
        self.check.backup_bgcheck_required_because)

  def test_check_upload_id_parsing_failed(self):
    self.test_upload_passport()

    self.api.check_passport_upload.return_value = {
        'success': False,
        'result': PARSING_FAILED,
        'description': 'blah blah blah'}
    self.api.get_test_result.return_value = {
        'backgroundCheck': {'hasCriminalRecord': None},
        'scannedUser': {
            'DateOfBirth': '11-04-81',
            'DateOfBirth4': '11-04-1981',
            'NameFirst': 'DAVID',
            'NameLast': 'SMITH',
            'NameMiddle': 'AARON',
            'IsOcrRead': True,
            'IsBarcodeRead': False}}
    self.authenticating_check.do_next_step(api=self.api)
    self.authenticating_check.refresh_from_db()

    self.assertEqual('ID parsing failed', self.authenticating_check.status())
    self.check.refresh_from_db()
    self.assertTrue(self.check.backup_bgcheck_required)
    self.assertEqual(
        'Unable to read barcode', self.check.backup_bgcheck_required_because)

  def test_get_test_result_to_scan_id_passport(self):
    self.test_check_passport_upload()
    # Here, Authenticating uses mm-dd-yy. But everywhere else it uses
    # dd-mm-yyyy
    self.api.get_test_result.return_value = {
        'backgroundCheck': {'hasCriminalRecord': None},
        'scannedUser': {
            'DateOfBirth': '11-04-81',
            'DateOfBirth4': '11-04-1981',
            'NameFirst': 'DAVID',
            'NameLast': 'SMITH',
            'NameMiddle': 'AARON',
            'IsOcrRead': True,
            'IsBarcodeRead': False}}
    self.authenticating_check.do_next_step(api=self.api)
    self.authenticating_check.refresh_from_db()
    expected_data = {
        'userAccessCode': 'd348165c-d942-4eac-b219-3e12132ae7dc'}
    self.assertEqual(
        [call(expected_data)], self.api.get_test_result.call_args_list)
    self.assertEqual('ID parsed', self.authenticating_check.status())
    bgcheck = self.authenticating_check.background_check
    self.assertEqual('DAVID', bgcheck.scanned_first_name)
    self.assertEqual('AARON', bgcheck.scanned_middle_name)
    self.assertEqual('SMITH', bgcheck.scanned_last_name)
    self.assertEqual(date(1981, 11, 4), bgcheck.scanned_dob)
    self.assertTrue(self.authenticating_check.able_to_read_front)
    self.assertFalse(self.authenticating_check.able_to_read_barcode)
    self.assertIsNone(self.authenticating_check.has_criminal_record)
    self.check.refresh_from_db()
    self.assertIsNone(self.check.passed)
    self.assertIsNone(self.check.completed_at)

  def test_update_user_passport(self):
    self.test_get_test_result_to_scan_id_passport()
    self.api.update_user.return_value = {}
    self.authenticating_check.do_next_step(api=self.api)
    self.authenticating_check.refresh_from_db()
    expected_data = {
        'userAccessCode': 'd348165c-d942-4eac-b219-3e12132ae7dc',
        'firstName': 'DAVID',
        'middleName': 'AARON',
        'lastName': 'SMITH',
        'dob': '04-11-1981',
        'email': 'davery@doo.dave',
        'ssn': None,
        'address': None,
        'city': None,
        'state': None,
        'zipCode': None}
    self.assertEqual(
        [call(expected_data)], self.api.update_user.call_args_list)
    self.assertEqual('User updated', self.authenticating_check.status())

  def test_verify_passport(self):
    self.test_update_user_passport()

    self.api.verify_passport.return_value = {'success': True}
    self.authenticating_check.do_next_step(api=self.api)
    self.authenticating_check.refresh_from_db()
    expected_data = {
        'userAccessCode': 'd348165c-d942-4eac-b219-3e12132ae7dc'}
    self.assertEqual(
        [call(expected_data)], self.api.verify_passport.call_args_list)
    self.assertEqual('ID valid', self.authenticating_check.status())

  def test_verify_id_fails(self):
    """ I don't know that it ever actually works like this. I suspect not
    actually. The following test about a specific failure is from real life.
    """
    self.test_update_user_passport()

    self.api.verify_passport.return_value = {'success': False}
    self.authenticating_check.do_next_step(api=self.api)
    self.check.refresh_from_db()
    self.assertTrue(self.check.backup_bgcheck_required)
    self.assertEqual(
        'verify_id failed', self.check.backup_bgcheck_required_because)

  def test_verify_id_fails_due_to_bar_code(self):
    self.test_update_user_passport()
    self.switch_to_us_id()

    self.api.verify_id.side_effect = NotOkError(
        400, (
            b'{"errorMessage":"We were unable to get a confident read of the '
            b'barcode on this document. Please try again or attempt to '
            b'verify yourself another way."}'), None, None)
    self.authenticating_check.do_next_step(api=self.api)
    self.authenticating_check.refresh_from_db()
    self.assertEqual('ID invalid', self.authenticating_check.status())
    error_message = (
        'We were unable to get a confident read of the '
        'barcode on this document. Please try again or attempt to '
        'verify yourself another way.')
    self.assertEqual(
        error_message, self.authenticating_check.id_verified_error_message)
    self.check.refresh_from_db()
    self.assertTrue(self.check.backup_bgcheck_required)
    self.assertEqual(
        'verify_id failed', self.check.backup_bgcheck_required_because)

  def test_run_background_check(self):
    self.test_verify_passport()

    self.api.run_background_check.return_value = {'success': True}
    self.authenticating_check.do_next_step(api=self.api)
    self.assertEqual('Awaiting results', self.authenticating_check.status())
    expected_data = {
        'userAccessCode': 'd348165c-d942-4eac-b219-3e12132ae7dc'}
    self.assertEqual(
        [call(expected_data)], self.api.run_background_check.call_args_list)

  def test_get_test_result_no_criminal_record(self):
    self.test_run_background_check()

    self.api.get_test_result.return_value = {
        'backgroundCheck': {'hasCriminalRecord': False}}
    self.authenticating_check.do_next_step(api=self.api)
    self.authenticating_check.refresh_from_db()

    # This api call happens early in the process to get the parsed information
    # off the ID. Then it happens again to actually look for the results.
    expected_data = {
        'userAccessCode': 'd348165c-d942-4eac-b219-3e12132ae7dc'}
    self.assertEqual(
        [call(expected_data), call(expected_data)],
        self.api.get_test_result.call_args_list)

    self.assertEqual('Done', self.authenticating_check.status())
    self.assertFalse(self.authenticating_check.has_criminal_record)
    self.check.refresh_from_db()
    # When Authenticating says they pass, they pass.
    self.assertTrue(self.check.passed)
    self.assertIsNotNone(self.check.completed_at)

  def test_get_test_result_has_criminal_record(self):
    self.test_run_background_check()

    self.api.get_test_result.return_value = {
        'backgroundCheck': {'hasCriminalRecord': True}}
    self.authenticating_check.do_next_step(api=self.api)
    self.authenticating_check.refresh_from_db()
    self.assertEqual('Done', self.authenticating_check.status())
    self.assertTrue(self.authenticating_check.has_criminal_record)
    self.check.refresh_from_db()
    # If we could trust Authenticating with FAIL results, we'd do this:
    """
    self.assertFalse(self.check.passed)
    self.assertIsNotNone(self.check.completed_at)
    """
    # But instead, when Authenticating says fail, we look further into the
    # matter.
    self.assertIsNone(self.check.passed)
    self.assertTrue(self.check.backup_bgcheck_required)
    self.assertEqual(
        'Authenticating says FAIL, but it might be a speeding ticket',
        self.check.backup_bgcheck_required_because)


class StatusTests(TestCase):
  def test_status(self):
    auth_check = get_test_authenticating_check()
    self.assertEqual('Created', auth_check.status())
    auth_check.consent_confirmed_on = str_to_tz_dt('2018-12-25 12:00')
    self.assertEqual('Consent confirmed', auth_check.status())
    auth_check.id_uploaded_on = str_to_tz_dt('2018-12-25 13:00')
    self.assertEqual('ID upload attempted', auth_check.status())
    auth_check.id_upload_result_last_checked_on = str_to_tz_dt(
        '2018-12-25 14:00')
    auth_check.id_upload_description = 'Whatever whatever.'
    auth_check.id_upload_result = PARSING_FAILED
    self.assertEqual('ID parsing failed', auth_check.status())
    auth_check.id_upload_result = COMPLETE
    auth_check.id_upload_success = True
    self.assertEqual('ID upload successful', auth_check.status())
    auth_check.id_verified_on = str_to_tz_dt('2018-12-25 15:00')
    auth_check.id_verified_result = False
    self.assertEqual('ID invalid', auth_check.status())
    auth_check.id_verified_result = True
    self.assertEqual('ID valid', auth_check.status())
    auth_check.has_criminal_record = True
    self.assertEqual('Done', auth_check.status())


class StillNeedWorkTests(TestCase):
  def test_still_need_work(self):
    just_started = get_test_authenticating_check(
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'))
    # Checkout in the past
    checkout_in_past = get_test_authenticating_check(
        check_in=str_to_tz_dt('2018-01-01 16:00'),
        check_out=str_to_tz_dt('2018-01-02 11:00'))
    # No longer the canonical background check for a reservation
    no_res = get_test_background_check(
        reservation=None, submission=get_test_submission())
    no_res_authenticating = get_test_authenticating_check(
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'), background_check=no_res)
    # Complete
    complete = get_test_authenticating_check(
        has_criminal_record=True, check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'))
    # Can't complete because, we're told, this isn't a real person.
    id_not_verified = get_test_authenticating_check(
        id_verified_result=False, check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'))
    # Can't complete because it couldn't read the photos perhaps because they
    # were too low quality or something.
    parsing_failed = get_test_authenticating_check(
        id_upload_result=PARSING_FAILED,
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'))
    incomplete_parsing = get_test_authenticating_check(
        id_upload_result=UNKNOWN_STATE,
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'))

    expected = [just_started, incomplete_parsing]
    got = list(AuthenticatingCheck.objects.still_need_work(
        nnow=str_to_tz_dt('2018-12-24 12:00')))
    self.assertEqual(set(expected), set(got))
    self.assertEqual(
        'Checkout in the past', checkout_in_past.explain_why_no_work_needed(
            nnow=str_to_tz_dt('2018-12-24 12:00')))
    self.assertEqual(
        'The background check does not have a reservation',
        no_res_authenticating.explain_why_no_work_needed(
            nnow=str_to_tz_dt('2018-12-24 12:00')))
    self.assertEqual('Complete', complete.explain_why_no_work_needed(
        nnow=str_to_tz_dt('2018-12-24 12:00')))
    self.assertEqual(
        'ID could not be verified',
        id_not_verified.explain_why_no_work_needed(
            nnow=str_to_tz_dt('2018-12-24 12:00')))
    self.assertEqual(
        'Parsing failed', parsing_failed.explain_why_no_work_needed(
            nnow=str_to_tz_dt('2018-12-24 12:00')))
    self.assertEqual('', just_started.explain_why_no_work_needed(
        nnow=str_to_tz_dt('2018-12-24 12:00')))
    self.assertEqual('', incomplete_parsing.explain_why_no_work_needed(
        nnow=str_to_tz_dt('2018-12-24 12:00')))
