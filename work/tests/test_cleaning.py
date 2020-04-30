import copy
from datetime import timedelta, date, datetime
from dateutil.parser import parse
from unittest.mock import Mock

from django.conf import settings
from django.utils.timezone import make_aware
from djmoney.money import Money

from bgcheck.tests.test_background_check import get_test_background_check
from errors.models import Notifier
from work.api import API
from work.api_examples import CREATE_JOB, CANCEL_JOB, BOOKING_CREATE
from work.models.cleaning import (
    Cleaning, CleaningConfig, Cleanable, post_reservation_sync)
from work.models.work import CREATED
from work.models.work_type import CLEANER
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_work import (
    get_test_independent_worker, set_work_stuff)
from work.tests.test_work_co import get_test_work_co
from work.tests.test_work_co_worker import get_test_work_co_worker
from rentals.tests import get_test_rental, get_test_building
from reservations.models import Reservation, CANCELED, CONFIRMED
from reservations.tests import get_test_reservation
from util.channels import AIRBNB, BOOKINGCOM
from util.signals import post_sync
from util.tests import TestCase, FakeResponse
from util.timezone import str_to_tz_dt, tz_dt_to_tz_dt, parse_dt, now


def get_test_cleaning(**kwargs):
  if 'reservation' in kwargs:
    reservation = kwargs['reservation']
  else:
    reservation = get_test_reservation(**kwargs)
  rental = kwargs.get('rental', None)
  if not rental:
    rental = reservation.rental
  if not rental.properlyrental_or_none:
    pr_kwargs = kwargs.copy()
    pr_kwargs['rental'] = rental
    get_test_properly_rental(**pr_kwargs)
  default_offered_start_time = None
  if reservation:
    default_offered_start_time = reservation.check_out + timedelta(minutes=15)
  kwargs['offered_start_time'] = kwargs.get(
      'offered_start_time', default_offered_start_time)
  cleaning = Cleaning(
      reservation=reservation, rental=rental,
      reviewed_by=kwargs.get('reviewed_by', None),
      reviewed_at=kwargs.get('reviewed_at', None))
  set_work_stuff(cleaning, **kwargs)
  return cleaning


def get_test_cleaning_config(**kwargs):
  properly_rental = kwargs.get('properly_rental', None)
  if not properly_rental:
    if 'rental' in kwargs:
      properly_rental = kwargs['rental'].properlyrental_or_none
  if not properly_rental:
    properly_rental = get_test_properly_rental(**kwargs)

  inspection_checklist_id = kwargs.get(
      'inspection_checklist_id', 'insparction')
  return CleaningConfig.objects.create(
      properly_rental=properly_rental,
      properly_checklist_id=kwargs.get('properly_checklist_id', 'charkloosta'),
      cleaning_checklist=kwargs.get('cleaning_checklist', None),
      inspection_checklist_id=inspection_checklist_id,
      cleaning_duration=kwargs.get('cleaning_duration', 3),
      message=kwargs.get('message', None))


class InitCleanablesTests(TestCase):
  def setUp(self):
    super().setUp()
    self.rental = get_test_rental()
    self.properly_rental = get_test_properly_rental(rental=self.rental)
    self.cleaning_checklist = get_test_cleaning_config(
        properly_rental=self.properly_rental)
    self.bgcheck_rental = get_test_rental(background_check_guests=True)
    get_test_cleaning_config(rental=self.bgcheck_rental)
    get_test_independent_worker(
        buildings=[self.rental.building, self.bgcheck_rental.building],
        email='mr_clean@clean.email')

    go_live = parse_dt(settings.PROPERLY_GOES_LIVE)
    self.nnow = go_live - timedelta(minutes=10)

    # A cleaning already exists but it's impermanently canceled.
    self.yes_1 = get_test_reservation(
        check_out=self.nnow + timedelta(hours=1), id_verified=True,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('100', 'USD'),
        rental=self.rental)
    self.canceled_cleaning = get_test_cleaning(
        reservation=self.yes_1, canceled_at=str_to_tz_dt('2018-05-15 12:00'))
    self.assertIsNone(
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            self.yes_1, self.nnow))

  def test_init_impermanently_canceled_cleaning_gets_clean_co_and_resets(self):
    self.properly_rental.clean_co = get_test_work_co()
    self.properly_rental.save()
    Cleaning.objects.create_in_keys(nnow=self.nnow)
    self.canceled_cleaning.refresh_from_db()
    self.assertEqual(CREATED, self.canceled_cleaning.status())

  def test_explain_why_cant_send_to_properly(self):
    no_cleaning_checklist_rental = get_test_rental(
        nickname='Borderless puzzle')
    properly_rental = get_test_properly_rental(
        rental=no_cleaning_checklist_rental, clean_co=get_test_work_co(),
        properly_property_id='', source_property_id='')
    reservation = get_test_reservation(
        check_out=self.nnow + timedelta(hours=1), id_verified=True,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('100', 'USD'),
        rental=no_cleaning_checklist_rental)
    cleanable = Cleanable(
        reservation=reservation, rental=properly_rental.rental,
        manual_cleaning=None)
    self.assertEqual(
        'Borderless puzzle doesn\'t have a cleaning config',
        Cleaning.objects.explain_why_cant_send_to_properly(
            cleanable))
    get_test_cleaning_config(properly_rental=properly_rental)
    self.assertEqual(
        'Borderless puzzle doesn\'t have a Properly ID',
        Cleaning.objects.explain_why_cant_send_to_properly(
            cleanable))

  def test_cleanables_require_create_and_explain_why_cant_create_cleanings(
      self):
    # A cleaning already exists, but it encountered a creation error and was
    # never actually kicked off.
    yes_2 = get_test_reservation(
        check_out=self.nnow + timedelta(hours=1), id_verified=True,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('100', 'USD'),
        rental=self.rental)
    get_test_cleaning(
        reservation=yes_2, creation_error='Wah things went wrong')
    self.assertIsNone(
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            yes_2, self.nnow))

    # A cleaning already exists but it's permanently canceled.
    has_permanently_canceled_cleaning = get_test_reservation(
        check_out=self.nnow + timedelta(hours=1), id_verified=True,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('100', 'USD'),
        rental=self.rental)
    permanently_canceled_cleaning = get_test_cleaning(
        reservation=has_permanently_canceled_cleaning,
        canceled_at=str_to_tz_dt('2018-05-15 12:00'),
        permanently_canceled_reason='Romy will handle this one.')
    self.assertEqual(
        'This reservation has a permanently canceled cleaning',
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            has_permanently_canceled_cleaning, self.nnow))

    airbnb_can_have_balance_due = get_test_reservation(
        # because they assume cc risk
        check_in=self.nnow, check_out=self.nnow + timedelta(days=6),
        id_verified=True, ideal_payin=Money('100', 'USD'),
        actual_payin=Money('100', 'USD'), rental=self.rental, channel=AIRBNB)
    self.assertIsNone(
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            airbnb_can_have_balance_due, self.nnow))

    has_a_cleaning_already = get_test_reservation(
        check_out=self.nnow + timedelta(days=6), id_verified=True,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('100', 'USD'),
        rental=self.rental)
    active_cleaning = get_test_cleaning(reservation=has_a_cleaning_already)
    self.assertEqual(
        'This reservation has all its cleanings already.',
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            has_a_cleaning_already, self.nnow))

    too_distant_indep = get_test_reservation(
        check_out=self.nnow + timedelta(days=8), id_verified=True,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('100', 'USD'),
        rental=self.rental)
    self.assertEqual(
        'The cleaning time is more than 7 days away',
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            too_distant_indep, self.nnow))

    id_not_verified = get_test_reservation(
        check_out=self.nnow + timedelta(hours=1), id_verified=False,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('100', 'USD'),
        rental=self.rental)
    self.assertEqual(
        'This guest\'s ID isn\'t verified',
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            id_not_verified, self.nnow))

    not_paid_in_full = get_test_reservation(
        check_out=self.nnow + timedelta(hours=1), id_verified=True,
        ideal_payin=Money('200', 'USD'), actual_payin=Money('100', 'USD'),
        rental=self.rental, channel=BOOKINGCOM)
    self.assertEqual(
        'This reservation has an outstanding balance of $100.00',
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            not_paid_in_full, self.nnow))

    no_cleaners_rental = get_test_rental()
    get_test_cleaning_config(rental=no_cleaners_rental)
    no_cleaners_available = get_test_reservation(
        check_out=self.nnow + timedelta(hours=1), id_verified=True,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('100', 'USD'),
        rental=no_cleaners_rental)
    self.assertEqual(
        'No independent cleaners are configured for this building',
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            no_cleaners_available, self.nnow))

    canceled_pre_checkin = get_test_reservation(
        check_in=self.nnow - timedelta(days=1),
        canceled_at=self.nnow - timedelta(days=2),
        status=CANCELED,
        check_out=self.nnow + timedelta(hours=1), id_verified=True,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('100', 'USD'),
        rental=self.rental)
    self.assertEqual(
        'This reservation was canceled before check in.',
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            canceled_pre_checkin, self.nnow))

    background_check_non_valid = get_test_reservation(
        check_in=self.nnow + timedelta(days=1),
        check_out=self.nnow + timedelta(days=2),
        status=CONFIRMED, id_verified=True,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('100', 'USD'),
        rental=self.bgcheck_rental)
    check = get_test_background_check(reservation=background_check_non_valid)
    self.assertEqual(
        'The background check is non-valid',  # Purposefully vague
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            background_check_non_valid, self.nnow))
    check.started_at = now()
    check.completed_at = now()
    check.passed = True
    check.save()
    self.assertIsNone(
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            background_check_non_valid, self.nnow))
    check.passed = False
    check.save()
    self.assertEqual(
        'The background check is non-valid',  # Purposefully vague
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            background_check_non_valid, self.nnow))

    canceled_post_checkin = get_test_reservation(
        check_in=self.nnow - timedelta(days=1),
        canceled_at=self.nnow,
        check_out=self.nnow + timedelta(days=1), id_verified=True,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('100', 'USD'),
        rental=self.rental)
    self.assertIsNone(
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            canceled_post_checkin, self.nnow))

    expected = [
        Cleanable(self.yes_1, self.rental, None),
        Cleanable(yes_2, self.rental, None),
        Cleanable(airbnb_can_have_balance_due, self.rental, None),
        Cleanable(canceled_post_checkin, self.rental, None)]
    cleanables_require_create_in_keys = list(sorted(
        Cleaning.objects.cleanables_require_create_in_keys(self.nnow),
        key=lambda x: x.reservation.pk))
    self.assertEqual(expected, cleanables_require_create_in_keys)

    # OK, sorry for this, it's a bit confusing. Now I'm going to test combo
    # units by making the existing unit the parent. Note that all reservations
    # are still against the parent rental as they should be. But now cleanables
    # reference the child unit.

    child = get_test_rental(building=self.rental.building)
    self.cleaning_checklist.properly_rental.rental = child
    self.cleaning_checklist.properly_rental.save()
    self.rental.is_combo_of.set([child])
    self.canceled_cleaning.rental = child
    self.canceled_cleaning.save()
    permanently_canceled_cleaning.rental = child
    permanently_canceled_cleaning.save()
    active_cleaning.rental = child
    active_cleaning.save()

    expected = [
        Cleanable(self.yes_1, child, None),
        Cleanable(yes_2, child, None),
        Cleanable(airbnb_can_have_balance_due, child, None),
        Cleanable(canceled_post_checkin, child, None)]
    cleanables_require_create_in_keys = list(sorted(
        Cleaning.objects.cleanables_require_create_in_keys(self.nnow),
        key=lambda x: x.reservation.pk))
    self.assertEqual(expected, cleanables_require_create_in_keys)


class BasicCleaningTests(TestCase):
  """ Base class. Put no actual tests in here. """
  def setUp(self):
    super().setUp()
    clean_co = get_test_work_co()
    self.properly_rental = get_test_properly_rental(clean_co=clean_co)
    get_test_cleaning_config(properly_rental=self.properly_rental)
    bob = get_test_work_co_worker(work_co=clean_co)
    self.cleaning = get_test_cleaning(
        job_request_id='', offered_to=[bob],
        rental=self.properly_rental.rental,
        check_in=str_to_tz_dt('2018-12-20 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'))
    self.api = Mock(spec=API)
    self.api.job_request_create.return_value = CREATE_JOB
    self.notifier = Mock(spec=Notifier)


class RetroactiveCheckoutTests(BasicCleaningTests):
  def test_retroactive_checkout(self):
    """ In the middle of a reservation, the check out gets changed to 2 days
    ago. The cleaning should happen next cleaning period. """
    self.assertEqual(
        str_to_tz_dt('2018-12-26 11:00'), self.cleaning.reservation.check_out)
    self.assertEqual(
        str_to_tz_dt('2018-12-26 11:15'), self.cleaning.offered_start_time)
    reservation = self.cleaning.reservation
    reservation.set_check_out(
        str_to_tz_dt('2018-12-22 11:00'),
        nnow=str_to_tz_dt('2018-12-24 12:00'))
    post_reservation_sync(
        Reservation, self.cleaning.reservation,
        nnow=str_to_tz_dt('2018-12-24 12:00'))
    self.cleaning.refresh_from_db()
    self.assertEqual(
        str_to_tz_dt('2018-12-25 11:15'),
        self.cleaning.offered_start_time)


class CleaningTests(TestCase):
  def test_reservation_checkout_changes_independent_cleaner(self):
    reservation = get_test_reservation(
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'))
    get_test_cleaning_config(rental=reservation.rental)
    get_test_independent_worker(
        buildings=[reservation.rental.building], work_types=[CLEANER])

    cleanable = Cleanable(
        reservation=reservation, rental=reservation.rental,
        manual_cleaning=None)
    cleaning = cleanable.init(Mock(spec=API), nnow=str_to_tz_dt('2018-05-10'))
    self.assertEqual(cleaning, reservation.cleaning_set.first())
    self.assertEqual(1, reservation.cleaning_set.count())
    self.assertEqual(
        str_to_tz_dt('2018-05-16 11:15'), cleaning.offered_start_time)

    reservation.set_check_out(
        str_to_tz_dt('2018-05-17 11:00'), nnow=str_to_tz_dt('2018-05-10'))
    reservation.save()
    post_sync.send(
        sender=Reservation, instance=reservation,
        nnow=str_to_tz_dt('2018-05-10'))

    cleaning.refresh_from_db()
    self.assertFalse(cleaning.canceled_at)  # Because it was rescheduled
    self.assertEqual(1, reservation.cleaning_set.count())
    cleaning.refresh_from_db()
    self.assertEqual(
        str_to_tz_dt('2018-05-17 11:15'),
        tz_dt_to_tz_dt(cleaning.offered_start_time))

  def test_get_start_time(self):
    self.assertEqual(
        None,
        Cleaning.objects.get_start_time(get_test_reservation(
            status=CANCELED,
            check_in=str_to_tz_dt('2018-10-15 16:00'),
            canceled_at=str_to_tz_dt('2018-10-15 15:00'),
            check_out=str_to_tz_dt('2018-10-17 11:00'))))
    self.assertEqual(
        str_to_tz_dt('2018-10-16 11:15'),
        Cleaning.objects.get_start_time(get_test_reservation(
            status=CANCELED,
            check_in=str_to_tz_dt('2018-10-15 16:00'),
            canceled_at=str_to_tz_dt('2018-10-16 9:00'),
            check_out=str_to_tz_dt('2018-10-17 11:00'))))
    self.assertEqual(
        str_to_tz_dt('2018-10-17 11:15'),
        Cleaning.objects.get_start_time(get_test_reservation(
            status=CANCELED,
            check_in=str_to_tz_dt('2018-10-15 16:00'),
            canceled_at=str_to_tz_dt('2018-10-16 12:00'),
            check_out=str_to_tz_dt('2018-10-17 11:00'))))
    self.assertEqual(
        str_to_tz_dt('2018-10-17 11:15'),
        Cleaning.objects.get_start_time(get_test_reservation(
            status=CANCELED,
            check_in=str_to_tz_dt('2018-10-15 16:00'),
            canceled_at=str_to_tz_dt('2018-10-17 12:00'),
            check_out=str_to_tz_dt('2018-10-17 11:00'))))
    self.assertEqual(
        str_to_tz_dt('2018-10-17 11:15'),
        Cleaning.objects.get_start_time(get_test_reservation(
            status=CONFIRMED,
            check_in=str_to_tz_dt('2018-10-15 16:00'),
            check_out=str_to_tz_dt('2018-10-17 11:00'))))

  def test_available_independent_cleaners(self):
    building = get_test_building()
    unrelated_building = get_test_building()
    res1 = get_test_reservation(
        check_in='2018-05-01 16:00', check_out='2018-05-02 11:00',
        rental=get_test_rental(building=building))
    get_test_cleaning_config(rental=res1.rental)
    res2 = get_test_reservation(
        check_in='2018-05-01 16:00', check_out='2018-05-02 11:00',
        rental=get_test_rental(building=building))
    get_test_cleaning_config(rental=res2.rental)
    mr_clean = get_test_independent_worker(buildings=[building])
    ms_clean = get_test_independent_worker(
        buildings=[building, unrelated_building], name='Ms Clean')
    get_test_independent_worker()  # unrelated_cleaner
    get_test_cleaning(reservation=res1, accepted_by=mr_clean)
    cleanable = Cleanable(
        reservation=res2, rental=res2.rental, manual_cleaning=None)

    self.assertEqual(
        [ms_clean], list(cleanable.available_independent_cleaners()))

  def test_create_in_keys(self):
    building = get_test_building()
    get_test_independent_worker(
        buildings=[building], email='mr_clean@clean.email')
    rental = get_test_rental(building=building)
    get_test_cleaning_config(
        properly_checklist_id='checkleast', rental=rental,
        cleaning_duration=7,
        properly_property_id='daves_source_id',
        source_property_id='daves_source_id', message='message here')
    get_test_reservation(
        check_in=parse('2018-11-19T15:00:00.000Z'),
        check_out=parse('2018-11-20T11:00:00.000Z'),
        channel_id='ibelieveinafingcalledlove',
        rental=rental, id_verified=True, ideal_payin=Money('100', 'USD'),
        actual_payin=Money('100', 'USD'))

    api = Mock(spec=API)
    api.job_request_create.return_value = CREATE_JOB

    cleanings = Cleaning.objects.create_in_keys(
        api=api, nnow=str_to_tz_dt('2018-11-18 12:00'))

    self.assertEqual(1, len(cleanings))
    cleaning = cleanings[0]
    # creation_confirmed isn't set now until a successful webhook comes back.
    self.assertEqual(cleaning.get_start_time(), cleaning.offered_start_time)
    self.assertEqual(
        parse('2018-11-20T11:15:00.000Z'), cleaning.get_start_time())

  def test_create_in_keys_combo(self):
    building = get_test_building()
    get_test_independent_worker(
        buildings=[building], email='mr_clean@clean.email')
    atom1 = get_test_rental(building=building, nickname='atom1')
    atom2 = get_test_rental(building=building, nickname='atom2')
    combo_rental = get_test_rental(
        building=building, is_combo_of=[atom1, atom2], nickname='combo')
    reservation = get_test_reservation(
        rental=combo_rental, check_in=str_to_tz_dt('2018-12-20 16:00'),
        check_out=str_to_tz_dt('2018-12-21 11:00'), id_verified=True)
    get_test_cleaning_config(
        properly_checklist_id='checklist1', rental=atom1, cleaning_duration=3,
        properly_property_id='blah1', source_property_id='blah1')
    get_test_cleaning_config(
        properly_checklist_id='checklist2', rental=atom2, cleaning_duration=3,
        properly_property_id='blah2', source_property_id='blah2')

    nnow = str_to_tz_dt('2018-12-18 12:00')

    self.assertFalse(
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            reservation, nnow=nnow))
    cleanings = Cleaning.objects.create_in_keys(api=Mock(spec=API), nnow=nnow)

    self.assertEqual(2, len(cleanings))
    self.assertEqual(2, reservation.cleaning_set.count())
    reservation.cleaning_set.get(rental=atom1)
    reservation.cleaning_set.get(rental=atom2)

  def test_reservation_rental_changes(self):
    nnow = str_to_tz_dt('2019-05-13 16:00')
    building = get_test_building()
    old_rental = get_test_rental(building=building, nickname='old rental')
    get_test_cleaning_config(rental=old_rental)
    new_rental = get_test_rental(building=building, nickname='new rental')
    get_test_cleaning_config(rental=new_rental)
    get_test_independent_worker(buildings=[building], work_types=[CLEANER])
    reservation = get_test_reservation(
        check_in=str_to_tz_dt('2019-05-15 16:00'),
        check_out=str_to_tz_dt('2019-05-16 11:00'), rental=old_rental,
        id_verified=True)
    get_test_cleaning(reservation=reservation, job_request_id='toldja')

    api = Mock(spec=API)
    api.job_request_create.return_value = CREATE_JOB
    api.job_request_cancel.return_value = CANCEL_JOB
    api.booking_create.return_value = FakeResponse(True, BOOKING_CREATE)

    reservation.rental = new_rental
    reservation.save()
    post_sync.send(
        sender=Reservation, instance=reservation, api=api, nnow=nnow)

    Cleaning.objects.get(
        reservation=reservation, rental=new_rental,
        offered_start_time=str_to_tz_dt('2019-05-16 11:15'))

  def test_reservation_checkout_changes_combo(self):
    building = get_test_building()
    atom1 = get_test_rental(building=building, nickname='atom1')
    atom2 = get_test_rental(building=building, nickname='atom2')
    combo_rental = get_test_rental(
        building=building, is_combo_of=[atom1, atom2])
    reservation = get_test_reservation(
        rental=combo_rental, check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'))
    get_test_cleaning_config(rental=atom1)
    get_test_cleaning_config(rental=atom2)
    get_test_independent_worker(buildings=[building], work_types=[CLEANER])
    get_test_independent_worker(buildings=[building], work_types=[CLEANER])
    get_test_cleaning(
        reservation=reservation, rental=atom1, job_request_id='old_id_1')
    get_test_cleaning(
        reservation=reservation, rental=atom2, job_request_id='old_id_1')

    reservation.set_check_out(
        str_to_tz_dt('2019-01-03 11:00'), nnow=str_to_tz_dt('2018-12-25'))
    post_sync.send(
        sender=Reservation, instance=reservation,
        nnow=str_to_tz_dt('2018-12-25'))

    self.assertEqual(2, reservation.cleaning_set.count())
    self.assertEqual(
        2, reservation.cleaning_set.filter(canceled_at__isnull=True).count())

  def test_reservation_canceled_after_checkin(self):
    rental = get_test_rental()
    reservation = get_test_reservation(
        rental=rental, status=CANCELED,
        canceled_at=str_to_tz_dt('2018-05-16 09:00'),
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-17 11:00'))
    get_test_cleaning_config(rental=rental)
    get_test_independent_worker(
        buildings=[reservation.rental.building], work_types=[CLEANER])
    cleaning = get_test_cleaning(
        reservation=reservation, job_request_id='first_id')

    api = Mock(spec=API)
    create_response = copy.deepcopy(CREATE_JOB)
    create_response['jobRequest.create'][0]['jobRequestId'] = 'second_id'
    api.job_request_cancel.return_value = CANCEL_JOB
    api.job_request_create.return_value = create_response
    post_sync.send(
        sender=Reservation, instance=reservation, api=api,
        nnow=str_to_tz_dt('2018-05-16 09:00'))

    cleaning.refresh_from_db()
    self.assertEqual('', cleaning.permanently_canceled_reason)
    new_cleaning = reservation.cleaning_set.get(canceled_at__isnull=True)
    self.assertEqual(
        str_to_tz_dt('2018-05-16 11:15'),
        tz_dt_to_tz_dt(new_cleaning.offered_start_time))

  def test_reservation_canceled_after_checkin_combo(self):
    building = get_test_building()
    get_test_independent_worker(buildings=[building])
    get_test_independent_worker(buildings=[building])
    atom1 = get_test_rental(building=building)
    atom2 = get_test_rental(building=building)
    get_test_cleaning_config(rental=atom1)
    get_test_cleaning_config(rental=atom2)
    combo_rental = get_test_rental(
        building=building, is_combo_of=[atom1, atom2])
    reservation = get_test_reservation(
        rental=combo_rental, status=CANCELED,
        canceled_at=str_to_tz_dt('2018-05-16 09:00'),
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-17 11:00'))
    get_test_cleaning(
        reservation=reservation, rental=atom1,
        offered_start_time=str_to_tz_dt('2018-05-17 11:15'))
    get_test_cleaning(
        reservation=reservation, rental=atom2,
        offered_start_time=str_to_tz_dt('2018-05-17 11:15'))

    post_sync.send(
        sender=Reservation, instance=reservation,
        nnow=str_to_tz_dt('2018-05-16 09:00'))

    self.assertEqual(2, reservation.cleaning_set.count())
    reservation.cleaning_set.filter(
        canceled_at__isnull=True,
        offered_start_time=str_to_tz_dt('2018-05-16 11:15'),
        rental=atom1)
    reservation.cleaning_set.filter(
        canceled_at__isnull=True,
        offered_start_time=str_to_tz_dt('2018-05-16 11:15'),
        rental=atom2)

  def test_reservation_canceled_before_checkin(self):
    rental = get_test_rental()
    reservation = get_test_reservation(
        rental=rental,
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'))
    get_test_cleaning_config(rental=rental)

    cleaning = get_test_cleaning(
        reservation=reservation, job_request_id='first_id')

    reservation.status = CANCELED
    reservation.canceled_at = str_to_tz_dt('2018-05-14 16:00')
    reservation.save()
    api = Mock(spec=API)
    api.job_request_cancel.return_value = CANCEL_JOB
    post_sync.send(sender=Reservation, instance=reservation, api=api)

    cleaning.refresh_from_db()
    self.assertEqual(
        'The reservation is now canceled',
        cleaning.permanently_canceled_reason)
    self.assertEqual(
        0, Cleaning.objects.filter(
            reservation=reservation, canceled_at__isnull=True).count())

  def test_soon_creates_cleaning_immediately(self):
    api = Mock(spec=API)

    building = get_test_building()
    get_test_independent_worker(
        buildings=[building], email='mr_clean@clean.email')
    rental = get_test_rental(building=building)
    get_test_cleaning_config(
        properly_checklist_id='checkleast', rental=rental, cleaning_duration=7,
        properly_property_id='daves_source_id',
        source_property_id='daves_source_id')

    nnow = parse('2018-11-14T11:15:00.000Z')

    soon = get_test_reservation(
        check_in=parse('2018-11-19T15:00:00.000Z'),
        check_out=parse('2018-11-20T11:00:00.000Z'),
        channel_id='heyyououtthereinthecold',
        rental=rental, id_verified=True, ideal_payin=Money('100', 'USD'),
        actual_payin=Money('100', 'USD'))
    post_sync.send(sender=Reservation, instance=soon, api=api, nnow=nnow)

    self.assertTrue(soon.cleaning_set.exists())

    not_soon = get_test_reservation(
        check_in=parse('2018-11-20T11:00:00.000Z'),
        check_out=parse('2018-11-21T11:00:00.000Z'),
        channel_id='canyouhearme',
        rental=rental, id_verified=True, ideal_payin=Money('100', 'USD'),
        actual_payin=Money('100', 'USD'))
    post_sync.send(sender=Reservation, instance=not_soon, api=api, nnow=nnow)

    self.assertFalse(not_soon.cleaning_set.exists())

  def test_confirmed_no_cleaning(self):
    rental = get_test_rental()
    get_test_cleaning_config(rental=rental)
    get_test_independent_worker(
        buildings=[rental.building], email='mr_clean@clean.email')

    get_test_reservation(  # Old
        booked_at=str_to_tz_dt('2018-11-01'),
        check_in=str_to_tz_dt('2018-11-29 16:00'),
        check_out=str_to_tz_dt('2018-11-30 11:00'), id_verified=False,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('0', 'USD'),
        rental=rental)
    get_test_reservation(  # More than 48 hours out
        check_in=str_to_tz_dt('2018-12-29 16:00'),
        check_out=str_to_tz_dt('2018-12-30 11:00'), id_verified=False,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('0', 'USD'),
        rental=rental)
    res_no_cleaning = get_test_reservation(
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'), id_verified=False,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('0', 'USD'),
        rental=rental)
    res_has_cleaning = get_test_reservation(
        check_in=str_to_tz_dt('2018-12-24 16:00'),
        check_out=str_to_tz_dt('2018-12-25 11:00'), id_verified=True,
        ideal_payin=Money('100', 'USD'), actual_payin=Money('100', 'USD'),
        rental=rental)
    get_test_cleaning(reservation=res_has_cleaning)

    cleanables = list(Cleaning.objects.confirmed_no_cleaning(
        nnow=str_to_tz_dt('2018-12-25'), within_hours=48))
    self.assertEqual(1, len(cleanables))
    self.assertEqual(res_no_cleaning, cleanables[0].reservation)

  def test_taking_too_long(self):
    get_test_cleaning(  # yesterday
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'),
        started_at=str_to_tz_dt('2018-05-16 11:15'),
        completed_at=str_to_tz_dt('2018-05-16 19:15'),
        accepted_by=get_test_independent_worker())
    get_test_cleaning(  # in progress but not too long
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-17 11:00'),
        started_at=str_to_tz_dt('2018-05-17 11:30'),
        completed_at=None,
        accepted_by=get_test_independent_worker())
    in_progress_too_long = get_test_cleaning(
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-17 11:00'),
        started_at=str_to_tz_dt('2018-05-17 11:15'),
        completed_at=None,
        accepted_by=get_test_independent_worker())
    self.assertFalse(in_progress_too_long.is_complete())
    get_test_cleaning(  # complete but not too long
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-17 11:00'),
        started_at=str_to_tz_dt('2018-05-17 11:30'),
        completed_at=str_to_tz_dt('2018-05-17 13:30'),
        accepted_by=get_test_independent_worker())
    complete_too_long = get_test_cleaning(
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-17 11:00'),
        started_at=str_to_tz_dt('2018-05-17 11:16'),
        completed_at=str_to_tz_dt('2018-05-17 14:50'),
        accepted_by=get_test_independent_worker())
    self.assertTrue(complete_too_long.is_complete())
    nnow = str_to_tz_dt('2018-05-17 14:55')
    self.assertEqual(
        [in_progress_too_long, complete_too_long],
        Cleaning.objects.taking_too_long(nnow))

  def test_still_cleaning_25_before_checkin(self):
    rental = get_test_rental()
    get_test_cleaning(  # Other rental
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'),
        started_at=str_to_tz_dt('2018-05-16 11:15'),
        accepted_by=get_test_independent_worker())
    taking_too_long = get_test_cleaning(
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'),
        started_at=str_to_tz_dt('2018-05-16 11:15'),
        accepted_by=get_test_independent_worker(), rental=rental)
    get_test_cleaning(  # Complete already
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'),
        started_at=str_to_tz_dt('2018-05-16 11:15'),
        completed_at=str_to_tz_dt('2018-05-16 15:00'),
        accepted_by=get_test_independent_worker(), rental=rental)
    get_test_reservation(
        rental=rental, check_in=str_to_tz_dt('2018-05-16 16:00'),
        check_out=str_to_tz_dt('2018-05-17 11:00'))
    self.assertEqual(
        [],
        Cleaning.objects.still_cleaning_25_before_checkin(
            str_to_tz_dt('2018-05-16 15:34')))
    self.assertEqual(
        [taking_too_long],
        Cleaning.objects.still_cleaning_25_before_checkin(
            str_to_tz_dt('2018-05-16 15:35')))

  def test_todays_jobs(self):
    today = date.today()
    cleaner = get_test_independent_worker()
    yes = get_test_cleaning(
        accepted_by=cleaner, reservation=get_test_reservation(
            check_out=make_aware(datetime(
                today.year, today.month, today.day, 11))))
    get_test_cleaning(  # Wrong day
        accepted_by=cleaner, reservation=get_test_reservation(
            check_out=make_aware(timedelta(days=1) + datetime(
                today.year, today.month, today.day, 11))))
    yes_2 = get_test_cleaning(  # No cleaner, still alert!
        accepted_by=None, reservation=get_test_reservation(
            check_out=make_aware(datetime(
                today.year, today.month, today.day, 11))))
    self.assertEqual(
        set([yes, yes_2]), set(list(Cleaning.objects.todays_jobs())))

  def test_uh_oh_unclaimed(self):
    cleaning = get_test_cleaning(
        accepted_by=None, reservation=get_test_reservation(
            check_out=str_to_tz_dt('2018-10-17 11:00')))
    Cleaning.objects.filter(pk=cleaning.pk).update(
        created_at=str_to_tz_dt('2018-10-15 08:00'))
    self.assertEqual([], list(Cleaning.objects.uh_oh_unclaimed(
        nnow=str_to_tz_dt('2018-10-15 11:14'))))
    self.assertEqual([cleaning], list(Cleaning.objects.uh_oh_unclaimed(
        nnow=str_to_tz_dt('2018-10-15 11:16'))))
    cleaning.accepted_by = get_test_independent_worker()
    cleaning.save()
    self.assertEqual([], list(Cleaning.objects.uh_oh_unclaimed(
        nnow=str_to_tz_dt('2018-10-15 11:16'))))
    Cleaning.objects.filter(pk=cleaning.pk).update(
        accepted_by=None, created_at=str_to_tz_dt('2018-10-15 10:00'))
    self.assertEqual([], list(Cleaning.objects.uh_oh_unclaimed(
        nnow=str_to_tz_dt('2018-10-15 12:59'))))
    self.assertEqual([cleaning], list(Cleaning.objects.uh_oh_unclaimed(
        nnow=str_to_tz_dt('2018-10-15 13:00'))))
