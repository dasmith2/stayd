from work.tests.test_cleaning import (
    get_test_cleaning, get_test_cleaning_config)
from work.tests.test_rental import get_test_properly_rental
from rentals.tests import get_test_rental
from reservations.tests import get_test_reservation
from typeform.tests import get_test_typeform
from util.tests import TestCase
from util.timezone import str_to_tz_dt
from work.tests.test_inspect import get_test_inspection
from work.tests.test_worker import get_test_independent_worker


class InspectionTests(TestCase):
  def test_create_properly_job_data(self):
    rental = get_test_rental()
    reservation = get_test_reservation(
        rental=rental, channel_id='hatersgonnahate',
        check_in=str_to_tz_dt('2018-10-15 16:00'),
        check_out=str_to_tz_dt('2018-10-16 11:00'))
    properly_rental = get_test_properly_rental(
        rental=rental, properly_property_id='oscarwildeshouse',
        source_property_id='oscarwildeshouse')
    get_test_cleaning_config(
        properly_rental=properly_rental, properly_checklist_id='charkloost',
        inspection_checklist_id='inparctloost', cleaning_duration=3)
    cleaning = get_test_cleaning(
        reservation=reservation,
        offered_start_time=str_to_tz_dt('2018-10-16 11:15'))
    inspector = get_test_independent_worker(
        name='Inspector Bond', email='bond@007.com')
    inspection = get_test_inspection(
        inspect_cleaning=cleaning, offered_to=[inspector],
        offered_start_time=str_to_tz_dt('2018-10-16 15:00'))

    def get_expected(typeform_id):
      inspection_url = (
          'https://stayd.typeform.com/to/{}'
          '?reservation_id=hatersgonnahate').format(typeform_id)
      return {
          'title': 'Inspection',
          'message': inspection_url,
          'sourceBookingId': 'hatersgonnahate',
          'receiveUpdates': True,
          'time': {
              'type': 'fixed',
              'startTime': '2018-10-16T19:00:00Z',
              'durationInHours': 1},
          'property': {'sourcePropertyId': 'oscarwildeshouse'},
          'checklists': [{'checklistId': 'inparctloost'}],
          'serviceProviders': [{'email': 'bond@007.com'}]}
    nnow = str_to_tz_dt('2018-10-13')
    self.assertEqual(
        get_expected('Jh1K4F'),
        inspection.create_properly_job_data(nnow=nnow))
    get_test_typeform(typeform_id='AAABBB', title='Cleaning inspection')
    self.assertEqual(
        get_expected('AAABBB'), inspection.create_properly_job_data(nnow=nnow))
