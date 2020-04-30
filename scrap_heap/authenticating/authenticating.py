""" This file is for authenticating.com stuff specifically. It knows about
everything in bgcheck and in id_verify, but none of that stuff knows about
Authenticating. """
from datetime import datetime, timedelta
import json

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from bgcheck.models.background_check import BackgroundCheck
from commands.models import background_command
from errors.models import log_error
from id_verify.models import PASSPORT, US_ID_FRONT_AND_BACK
from photos.s3 import S3
from util import rrequests
from util.background import background
from util.fields import OneToOneOrNoneField
from util.html_status_codes import raise_if_not_ok, NotOkError
from util.timezone import now


# The id was received and successfully parsed.
COMPLETE = 'complete'
# Unable to detect the image. This can be caused by poor quality photos, bad
# lighting, glares, or other things that interfere with the image. Please try
# again and make sure that the id is on a contrasted surface (i.e. a white ID
# on a black background or a black id on a white background).
PARSING_FAILED = 'parsing_failed'
# This indicates that the call to checkUploadId has either been made too
# quickly after the image was uploaded or there has yet to be any image
# uploaded to the uploadId endpoint. If this result is received and an image
# has been sent to uploadId, try again after 20 seconds.
UNKNOWN_STATE = 'unknown_state'
# An unknown error has occurred. Please try again in a few moments.
UNKNOWN_ERROR = 'unknown_error'


ID_UPLOAD_RESULT_CHOICES = (
    (COMPLETE, COMPLETE),
    (PARSING_FAILED, PARSING_FAILED),
    (UNKNOWN_STATE, UNKNOWN_STATE),
    (UNKNOWN_ERROR, UNKNOWN_ERROR))


@receiver(post_save, sender=BackgroundCheck)
def post_save_background_check(sender, instance, *args, **kwargs):
  if explain_why_no_create_authenticating_bgcheck(instance):
    return
  api = kwargs.get('api', None)
  if api or settings.PROD:
    kick_off_authenticating_background_check(instance, api=api)


def explain_why_no_create_authenticating_bgcheck(bgcheck):
  if not bgcheck.submission:
    return 'No submission'
  if bgcheck.completed_at:
    return 'Bgcheck complete'
  if bgcheck.backup_bgcheck_required:
    return 'Backup required: {}'.format(
        bgcheck.backup_bgcheck_required_because)
  if bgcheck.authenticatingcheck_or_none:
    return 'Exists already'


@background
def kick_off_authenticating_background_check(
    background_check, manual=False, api=None):
  if not settings.TEST and not settings.AUTHENTICATING_COMPANY_ADMIN_KEY:
    raise Exception('AUTHENTICATING_COMPANY_ADMIN_KEY doesnt exist')
  background_check.started_at = now()
  background_check.save()
  check = AuthenticatingCheck.objects.create_new_check(
      background_check, manual=manual, api=api)
  check.do_next_steps(api=api)
  return check


@background_command
def do_authenticating_background_check_stuff_background(nnow=None):
  """ Push everything along in the process. """
  for check in AuthenticatingCheck.objects.still_need_work(nnow=nnow):
    check.do_next_steps()


class AuthenticatingCheckManager(models.Manager):
  def still_need_work(self, nnow=None):
    nnow = nnow or now()
    id_upload_could_be_valid = ~Q(id_upload_result=PARSING_FAILED)
    id_could_be_valid = ~Q(id_verified_result=False)
    no_final_result = Q(has_criminal_record__isnull=True)
    return self.filter(
        id_upload_could_be_valid & id_could_be_valid & no_final_result,
        background_check__reservation__check_out__gte=nnow,
        background_check__reservation__isnull=False)

  def create_new_check(
      self, background_check, manual=False, api=None, nnow=None):
    nnow = nnow or now()
    new_user = self._create_new_user(background_check, api)
    return_me = self.create(
        background_check=background_check,
        user_access_code=new_user['userAccessCode'],
        manual=manual)
    background_check.started_at = nnow
    background_check.save()
    return return_me

  def _create_new_user_data(self, background_check):
    guest = background_check.submission.reservation.guest
    return {
        # Required
        'firstName': guest.first_name,
        'lastName': guest.last_name,
        'dob': background_check.submission.birthday.strftime('%d-%m-%Y'),
        'email': background_check.reservation.get_email(),
        # Not required
        'middleName': None,
        'ssn': None,
        'address': None,
        'city': None,
        'state': None,
        'zipCode': None}

  def _create_new_user(self, background_check, api=None):
    api = api or API()
    return api.create_user(self._create_new_user_data(background_check))


class AuthenticatingCheck(models.Model):
  """ This class represents the state we need in order to move a background
  check through the whole automated Authenticating background check API
  process. """
  # CASCADE because BackgroundCheck has all this beautiful logic about deleting
  # in a timely manner.
  background_check = OneToOneOrNoneField(
      BackgroundCheck, on_delete=models.CASCADE)

  # Create User https://api-v3.authenticating.com/user/create
  user_access_code = models.CharField(
      unique=True, max_length=200, help_text=(
          'This is basically Authenticating\'s unique ID per background '
          'check.'))

  # Submit User Consent https://api-v3.authenticating.com/user/consent
  consent_confirmed_on = models.DateTimeField(
      null=True, blank=True, help_text=(
          'When did we get back a response from Authenticating telling us '
          'they got the consent confirmation?'))

  manual = models.BooleanField(default=False, help_text=(
      'Set this to true if youre pushing a background check through the steps '
      'manually for debugging purposes.'))

  def explain_why_no_work_needed(self, nnow=None):
    nnow = nnow or now()
    if self.id_upload_result == PARSING_FAILED:
      """
      https://api-v3.authenticating.com/identity/passport/scan/status
      {
        "success": false,
        "result": "parsing_failed",
        "numAttemptsLeft": 0,
        "description": "Text extraction was not successful. This can be caused
        by poor quality photos, bad lighting, glares, or other things that
        interfere with the image. Please try again and make sure that the id is
        on a contrasted surface (i.e. a white ID on a black background or a
        black id on a white background)."
      }
      """
      return 'Parsing failed'
    if self.id_verified_result is False:
      return 'ID could not be verified'
    if self.has_criminal_record is not None:
      return 'Complete'
    if not self.background_check.reservation:
      return 'The background check does not have a reservation'
    if self.background_check.reservation.check_out < nnow:
      return 'Checkout in the past'
    return ''

  def submit_user_consent(self, api=None):
    api = api or API()
    guest = self.background_check.submission.reservation.guest
    data = {
        'userAccessCode': self.user_access_code,
        'isReportChecked': 1,
        'isBackgroundDisclosureAccepted': 1,
        'fullName': guest.full_name}
    got = api.submit_user_consent(data)
    if got['success']:
      self.consent_confirmed_on = now()
      self.save()
      return True
    message = '{} {}'.format(self.pk, json.dumps(got, indent=2))
    log_error('Consent not submitted but no server error?', message)

  # Upload ID https://api-v2.authenticating.com/identity/document/scan I'm
  # wondering if that api-v2 business is a typo.
  id_uploaded_on = models.DateTimeField(
      null=True, blank=True, help_text=(
          'When did we upload the ID for this reservation to Authenticating?'))

  def upload_id(self, api=None, s3=None, nnow=None):
    api = api or API()
    s3 = s3 or S3(sensitive=True)
    nnow = nnow or now()
    submission = self.background_check.submission
    id_file_name = submission.id_photo_file_name()
    id_back_name = submission.id_back_file_name()
    if self._is_us_id():
      response = self._upload_us_id(id_file_name, id_back_name, api, s3)
    else:
      response = self._upload_passport(id_file_name, api, s3)
    if response['success']:
      self.id_uploaded_on = nnow
      self.save()

  def _upload_us_id(self, id_file_name, id_back_name, api, s3):
    data = {
        'userAccessCode': self.user_access_code,
        'idFront': s3.utf8_encoded_image(id_file_name),
        'idBack': s3.utf8_encoded_image(id_back_name),
        # https://docs.authenticating.com/#supported-countries
        'country': 0}
    return api.upload_id(data)

  def _upload_passport(self, id_file_name, api, s3):
    data = {
        'userAccessCode': self.user_access_code,
        'idFront': s3.utf8_encoded_image(id_file_name)}
    return api.upload_passport(data)

  # Check Upload ID
  # https://api-v3.authenticating.com/identity/document/scan/status
  id_upload_result_last_checked_on = models.DateTimeField(
      null=True, blank=True, help_text=(
          'When did we last check to see what the status of the ID upload '
          'was?'))
  id_upload_result = models.CharField(
      choices=ID_UPLOAD_RESULT_CHOICES, max_length=20, default='', blank=True,
      help_text=(
          'The last time we checked the id upload result, what was the '
          'status name?'))
  id_upload_description = models.TextField(
      default='', blank=True, help_text=(
          'The last time we checked the id upload result, what was the '
          'detailed description that came with the status?'))
  id_upload_success = models.BooleanField(
      null=True, blank=True, help_text=(
          'What was the success attribute of the .../scan/status call?'))

  def _user_access_code_only_data(self):
    return {'userAccessCode': self.user_access_code}

  def check_upload(self, api=None, nnow=None):
    api = api or API()
    nnow = nnow or now()
    if self._is_us_id():
      response = api.check_id_upload(self._user_access_code_only_data())
    else:
      response = api.check_passport_upload(self._user_access_code_only_data())
    self.id_upload_result_last_checked_on = now()
    self.id_upload_result = response['result']
    self.id_upload_description = response['description']
    self.id_upload_success = response['success']
    self.save()
    if not self.id_upload_success:
      if self.id_upload_result == PARSING_FAILED:
        self.background_check.backup_bgcheck_required = True
        self.background_check.backup_bgcheck_required_because = (
            'PARSING_FAILED')
        self.background_check.save()
        # Weirdly, the most common reason WHY this fails, a.k.a. can't read
        # barcode, is included in the test_result.
        self.get_test_result(api=api)
        if self.able_to_read_front and not self.able_to_read_barcode:
          self.background_check.backup_bgcheck_required_because = (
              'Unable to read barcode')
          self.background_check.save()
      elif self.id_upload_result == UNKNOWN_STATE:
        if self.id_uploaded_on + timedelta(hours=1) <= nnow:
          self.background_check.backup_bgcheck_required = True
          self.background_check.backup_bgcheck_required_because = (
              'Check upload stuck')
          self.background_check.save()
      elif self.id_upload_result != UNKNOWN_ERROR:
        raise Exception((
            'Not sure how to handle id_upload_success {} and '
            'result {}. {}').format(
                self.id_upload_success, self.id_upload_result, self.pk))

  # Get Test Result https://api-v3.authenticating.com/user/getTestResult
  has_criminal_record_checked_on = models.DateTimeField(
      null=True, blank=True, help_text=(
          'When did we do the first pass check to see if they have a criminal '
          'record?'))
  has_criminal_record = models.BooleanField(
      null=True, blank=True, help_text=(
          'And what were the results of the first pass check for a criminal '
          'record?'))
  raw_test_result = models.TextField(default='', blank=True)

  # These scanned_* fields are in background_check now. Delete these
  # eventually.
  scanned_first_name = models.CharField(max_length=200, default='', help_text=(
      'What first name came back from the get_test_result call?'))
  scanned_middle_name = models.CharField(
      max_length=200, default='', help_text=(
          'What middle name came back from the get_test_result call?'))
  scanned_last_name = models.CharField(max_length=200, default='', help_text=(
      'What last name came back from the get_test_result call?'))
  scanned_dob = models.DateField(null=True, help_text=(
      'What date of birth came back from the get_test_result call?'))

  able_to_read_front = models.BooleanField(null=True, blank=True, help_text=(
      'This comes from scannedUser["IsOcrRead"]'))
  able_to_read_barcode = models.BooleanField(null=True, blank=True, help_text=(
      'The barcode is on the back. '
      'This comes from scannedUser["IsBarcodeRead"]'))

  def no_scanned_user(self):
    """ Is it the case that Authenticating return no scannedUser field in
    get_test_result, a.k.a., they were unable to parse information off the ID?
    """
    return self.has_criminal_record_checked_on and not (
        self.background_check.scanned_first_name or (
            self.background_check.scanned_last_name))

  def get_test_result(self, api=None):
    """ This gets called twice as part of the workflow. At first it's to get
    the scanned info off the ID. Then later after the ID is verified, I call it
    again to get the result of the criminal background check. """
    api = api or API()
    response = api.get_test_result(self._user_access_code_only_data())
    self.has_criminal_record_checked_on = now()
    self.raw_test_result = json.dumps(response, indent=2)
    self.save()
    if 'scannedUser' in response and response['scannedUser']:
      user_data = response['scannedUser']
      self.able_to_read_front = user_data['IsOcrRead']
      self.able_to_read_barcode = user_data['IsBarcodeRead']
      if self.able_to_read_front:
        self.background_check.scanned_first_name = user_data['NameFirst']
        self.background_check.scanned_middle_name = user_data['NameMiddle']
        self.background_check.scanned_last_name = user_data['NameLast']
        self.background_check.scanned_dob = datetime.strptime(
            user_data['DateOfBirth4'], '%m-%d-%Y').date()
        self.background_check.save()
      else:
        id_verification_status = response.get(
            'idVerification', {}).get('status', None)
        if id_verification_status == 'FAILED':
          self.background_check.backup_bgcheck_required_because = (
              'Couldnt read the text on the ID')
          self.background_check.backup_bgcheck_required = True
          self.background_check.save()
      self.save()
    else:
      self.background_check.backup_bgcheck_required_because = (
          'get_test_result returned no scannedUser')
      self.background_check.backup_bgcheck_required = True
      self.background_check.save()
    if 'backgroundCheck' in response:
      check_data = response['backgroundCheck']
      if 'hasCriminalRecord' in check_data:
        has_criminal_record = check_data['hasCriminalRecord']
        if has_criminal_record is True or has_criminal_record is False:
          self.has_criminal_record = has_criminal_record
          self.save()
          if has_criminal_record:
            self.background_check.backup_bgcheck_required_because = (
                'Authenticating says FAIL, but it might be a speeding ticket')
            self.background_check.backup_bgcheck_required = True
          else:
            # Wouldn't it be rad if we could do this for fails as well? But
            # Authenticating is failing for, like, parking violations at the
            # moment. So the new strategy is, use Authenticating to hopefully
            # filter out the easily passing checks. But then we have to look
            # into the matter further when our suspicions are aroused.
            self.background_check.passed = not has_criminal_record
            self.background_check.completed_at = now()
          self.background_check.save()
          return

  user_updated_at = models.DateTimeField(
      null=True, blank=True, help_text=(
          'When did we update the user object with the results of '
          'get_test_result?'))

  def update_user(self, api=None):
    if not self.background_check.scanned_first_name:
      raise Exception(
          'You have to call get_test_result first so you can get the full '
          'name off the ID')
    api = api or API()
    api.update_user(self._update_user_data())
    self.user_updated_at = now()
    self.save()

  def _update_user_data(self):
    email = self.background_check.submission.reservation.guest.email
    return {
        # Required
        'userAccessCode': self.user_access_code,
        'firstName': self.background_check.scanned_first_name,
        'middleName': self.background_check.scanned_middle_name,
        'lastName': self.background_check.scanned_last_name,
        'dob': self.background_check.scanned_dob.strftime('%d-%m-%Y'),
        'email': email,
        # Not required
        'ssn': None,
        'address': None,
        'city': None,
        'state': None,
        'zipCode': None}

  # Verify Upload ID
  # https://api-v3.authenticating.com/identity/document/scan/data This call is
  # neccessary to make sure that the ID verification is complete for that
  # particular user. If this call is not completed, calls like Generate
  # Criminal Background Report will throw an error indicating the ID
  # verification has to be completed first.
  id_verified_on = models.DateTimeField(
      null=True, blank=True, help_text=(
          'When did we last check to see what the status of the ID upload '
          'was?'))
  id_verified_result = models.BooleanField(
      null=True, blank=True, help_text=(
          'Was the ID verified to be a real person? Note that no background '
          'check happened yet.'))
  id_verified_error_message = models.TextField(
      default='', help_text='If ID verification failed, did they explain why?')

  def verify_id(self, api=None):
    api = api or API()
    try:
      if self._is_us_id():
        response = api.verify_id(self._user_access_code_only_data())
      else:
        response = api.verify_passport(self._user_access_code_only_data())
      # This is just, like, {"success": False}
      self.id_verified_result = response['success']
    except NotOkError as ex:
      if ex.status_code == 400:
        self.id_verified_result = False
        got_data = json.loads(ex.content.decode('utf-8'))
        self.id_verified_error_message = got_data['errorMessage']
      else:
        raise ex
    self.id_verified_on = now()
    self.save()

    if not self.id_verified_result:
      self.background_check.backup_bgcheck_required = True
      self.background_check.backup_bgcheck_required_because = (
          'verify_id failed')
      self.background_check.save()

  background_check_run_on = models.DateTimeField(
      null=True, blank=True, help_text=(
          'When did we actually run the background check?'))

  def run_background_check(self, api=None):
    api = api or API()
    data = {'userAccessCode': self.user_access_code}
    api.run_background_check(data)
    self.background_check_run_on = now()
    self.save()

  objects = AuthenticatingCheckManager()

  def status(self):
    if self.has_criminal_record is not None:
      # The same API call is used to get the final result that's used to get
      # the parsed ID information
      return 'Done'
    if self.background_check_run_on:
      return 'Awaiting results'
    if self.id_verified_result is True:
      return 'ID valid'
    if self.id_verified_result is False:
      return 'ID invalid'
    if self.user_updated_at:
      return 'User updated'
    if self.id_upload_result == PARSING_FAILED:
      return 'ID parsing failed'
    if self.has_criminal_record_checked_on:
      # The same API call is used to get the final result, to get the parsed ID
      # information, and to get the reason why parsing failed. So, check this
      # after id_upload_result.
      return 'ID parsed'
    if self.id_upload_success:
      return 'ID upload successful'
    if self.id_uploaded_on:
      return 'ID upload attempted'
    if self.consent_confirmed_on:
      return 'Consent confirmed'
    return 'Created'

  def do_next_steps(self, api=None, s3=None):
    status_changed = True
    status = self.status()
    while status_changed and (
        not self.background_check.backup_bgcheck_required and (
            status != 'Done')):
      self.do_next_step()
      status_changed = status != self.status()
      status = self.status()

  def do_next_step(self, api=None, s3=None):
    if self.status() == 'Created':
      self.submit_user_consent(api=api)
    elif self.status() == 'Consent confirmed':
      self.upload_id(api=api, s3=s3)
    elif self.status() == 'ID upload attempted':
      self.check_upload(api=api)
    elif self.status() == 'ID upload successful':
      self.get_test_result(api=api)
    elif self.status() == 'ID parsed':
      self.update_user(api=api)
    elif self.status() == 'User updated':
      self.verify_id(api=api)
    elif self.status() == 'ID valid':
      self.run_background_check(api=api)
    elif self.status() == 'Awaiting results':
      self.get_test_result(api=api)
    else:
      raise Exception(
          'Not sure what to do next on {} with status {}'.format(
              self.pk, self.status()))

  def _is_us_id(self):
    id_type = self.background_check.submission.id_type
    if id_type == US_ID_FRONT_AND_BACK:
      return True
    elif id_type == PASSPORT:
      return False
    else:
      log_error(
          'Cant say if is_us_id because id_type is {}'.format(id_type),
          str(self.pk))


class API(object):
  def create_user(self, data, print_curl=True):
    return self._post('user/create', data, print_curl=print_curl)

  def update_user(self, data, print_curl=True):
    return self._put('user/update', data, print_curl=print_curl)

  def submit_user_consent(self, data, print_curl=True):
    return self._post('user/consent', data, print_curl=print_curl)

  def upload_passport(self, data, print_curl=False):
    return self._post('identity/passport/scan', data, print_curl=print_curl)

  def check_passport_upload(self, data, print_curl=True):
    return self._post(
        'identity/passport/scan/status', data, print_curl=print_curl)

  def verify_passport(self, data, print_curl=True):
    return self._post(
        'identity/passport/scan/data', data, print_curl=print_curl)

  def upload_id(self, data, print_curl=False):
    return self._post('identity/document/scan', data, print_curl=print_curl)

  def check_id_upload(self, data, print_curl=True):
    return self._post(
        'identity/document/scan/status', data, print_curl=print_curl)

  def get_test_result(self, data, print_curl=True):
    return self._post(
        'user/getTestResult', data, print_curl=print_curl)

  def verify_id(self, data, print_curl=True):
    return self._post(
        'identity/document/scan/data', data, print_curl=print_curl)

  def run_background_check(self, data, print_curl=True):
    return self._post(
        'user/generateCriminalReport', data, print_curl=print_curl)

  def _put(self, endpoint, data, print_curl=True):
    got = rrequests.put(
        self._url(endpoint), headers=self._headers(), json=data,
        print_curl=print_curl)
    raise_if_not_ok(got)
    data = got.json()

    print('Returned:')
    print(json.dumps(data, indent=2))

    return data

  def _post(self, endpoint, data, print_curl=True):
    got = rrequests.post(
        self._url(endpoint), headers=self._headers(), json=data,
        print_curl=print_curl)
    raise_if_not_ok(got)
    data = got.json()

    print('Returned:')
    print(json.dumps(data, indent=2))

    return data

  def _headers(self):
    return {'Authorization': 'Bearer {}'.format(
        settings.AUTHENTICATING_COMPANY_ADMIN_KEY)}

  def _url(self, endpoint):
    if endpoint[0] == '/':
      endpoint = endpoint[1:]
    return '{}/{}'.format(settings.AUTHENTICATING_API_ROOT, endpoint)
