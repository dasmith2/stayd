""" The point of this file is to set up testing data so I can run the entire
authenticating flow back to front locally for purposes of development.

from bgcheck.models.authenticating import AuthenticatingCheck
from bgcheck.tests.test_authenticating_flow import (
    get_bgcheck_submission, get_background_check, TestS3)

submission = get_bgcheck_submission(
    '../dave_id_front.jpg', '../dave_id_back.jpg')
check = get_background_check(submission)
ac = AuthenticatingCheck.objects.create_new_check(check)
ac.submit_user_consent()
s3 = TestS3()
ac.upload_id(s3=s3)
ac.check_upload()
# This gets the info parsed off the ID.
ac.get_test_result()
# Use the info parsed off the ID to update the user object
ac.update_user()
# Otherwise this step will be like, "I couldn't scan the bar code" when what it
# really means is, the barcode includes a middle name but we don't really get
# middle names from our guests.
ac.verify_id()
# Finally we can request a background check.
ac.run_background_check()
# But we have to poll until we get an answer.
ac.get_test_result()
"""
import base64
from datetime import date, timedelta

from django.conf import settings
from djmoney.money import Money

from bgcheck.tests.test_background_check import get_test_background_check
from guests.models import Guest
from guests.tests import get_test_guest
from id_verify.models import US_ID_FRONT_AND_BACK, ID, BACK_OF_ID
from id_verify.tests import get_test_submission, get_test_submission_photo
from rentals.models import Building
from rentals.tests import get_test_building, get_test_rental
from reservations.tests import get_test_reservation
from util.tests import get_test_user
from util.timezone import now


class TestS3(object):
  def utf8_encoded_image(self, file_name):
    with open(file_name, 'rb') as f:
      return base64.b64encode(f.read()).decode('utf-8')


def get_background_check(submission=None):
  if settings.PROD:
    raise Exception('Dont test on prod')
  if not submission:
    submission = get_bgcheck_submission()
  background_check = submission.backgroundcheck_or_none
  if not background_check:
    background_check = get_test_background_check(
        reservation=submission.reservation, submission=submission)
  return background_check


def get_bgcheck_submission(
    id_front_file_path, id_back_file_path=None, reservation=None,
    birthday=date(1981, 11, 4), id_type=US_ID_FRONT_AND_BACK):
  if settings.PROD:
    raise Exception('Dont test on prod')
  if not reservation:
    reservation = get_bgcheck_reservation()
  submission = reservation.submission_set.first()
  if not submission:
    submission = get_test_submission(
        email=reservation.guest.email, resized=True, reservation=reservation,
        id_matches_res=True, checked_at=now(), checked_by=get_test_user(),
        birthday=birthday, id_type=id_type)
    assert submission.all_good()
    get_test_submission_photo(
        submission=submission, photo_type=ID,
        file_name=id_front_file_path)
    if id_back_file_path:
      get_test_submission_photo(
          submission=submission, photo_type=BACK_OF_ID,
          file_name=id_back_file_path)
  return submission


def get_bgcheck_reservation(guest=None):
  if settings.PROD:
    raise Exception('Dont test on prod')
  if not guest:
    guest = get_bgcheck_guest()
  rental = get_bgcheck_rental()
  check_in = now().replace(
      hour=16, minute=0, second=0, microsecond=0) + timedelta(days=4)
  check_out = now().replace(
      hour=11, minute=0, second=0, microsecond=0) + timedelta(days=5)
  reservation = get_test_reservation(
      guest=guest, rental=rental, check_in=check_in, check_out=check_out,
      room_line_item=Money('100', 'USD'), booked_at=now())
  return reservation


def get_bgcheck_guest(
    first_name='David', last_name='Smith', email='dave@hihoward.com'):
  if settings.PROD:
    raise Exception('Dont test on prod')
  full_name = '{} {}'.format(first_name, last_name)
  guest = Guest.objects.filter(full_name=full_name).first()
  if not guest:
    guest = get_test_guest(
        full_name=full_name,
        first_name=first_name,
        last_name=last_name,
        phone='555-555-5555',
        email=email)
  return guest


def get_bgcheck_rental():
  if settings.PROD:
    raise Exception('Dont test on prod')
  building = get_bgcheck_building()
  rental = building.rental_set.filter(
      is_active=True, is_test_rental=False).first()
  if not rental:
    apt = '#56'
    full_address = '{} {}, {}, {}, {}'.format(
        building.street, apt, building.city, building.state,
        building.zipcode)
    rental = get_test_rental(
        building=building, full_address=full_address, street=building.street,
        apartment=apt, nickname='{} {}'.format(building.nickname, apt))
  return rental


def get_bgcheck_building():
  if settings.PROD:
    raise Exception('Dont test on prod')
  building = Building.objects.filter(
      background_check_guests=True, is_active=True).first()
  if not building:
    building = get_test_building(
        city='Hartford', state='CT', street='114 Woodland St.',
        zipcode='06105', nickname='St. Francis',
        background_check_guests=True)
  return building
