from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse
from djmoney.money import Money

from rentals.models import Rental, Building
from rentals.tests import get_test_rental, get_test_building
from util.permission import CLEANING_ADMINISTRATOR_GROUP
from util.web_test_users import get_web_test_user
from util.timezone import now
from work.models.maintenance_checklist import MaintenanceChecklist
from work.models.cleaning import Cleaning, CleaningConfig
from work.models.cleaning_checklist import CleaningChecklist
from work.models.delete import (
    delete_all_cleaning_checklists, delete_building, delete_cleaning,
    delete_maintenance)
from work.models.maintenance import Maintenance
from work.models.rental import ProperlyRental
from work.models.sla import NEXT_CHECKOUT
from work.models.work_co import WorkCo
from work.models.worker import IndependentWorker, Worker
from work.tests.test_maintenance_checklist import (
    get_test_maintenance_checklist)
from work.tests.test_cleaning import (
    get_test_cleaning, get_test_cleaning_config)
from work.tests.test_maintenance import get_test_maintenance
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_ticket import get_test_ticket
from work.tests.test_work_co import get_test_work_co
from work.tests.test_work_co_worker import get_test_work_co_worker
from work.tests.test_worker import get_test_independent_worker


INDEPENDENT_WORKER_USERNAME = 'independentsteve'
CLEANING_ADMINISTRATOR_USERNAME = 'cleaningadmin'
CLEAN_CO_OWNER_USERNAME = 'cleanco_owner'
CLEAN_CO_CLARANCE_USERNAME = 'cleanco_clarance'
CLEAN_CO_BOB_USERNAME = 'cleanco_bob'


def get_a_bunch_of_cleanings_for_web_tests(
    request, cleaning_checklist_pk=None):
  if settings.PROD:
    raise Exception('Dont create test data on prod.')
  _clear_out_old_web_test_cleanings()
  example_cleaning = _create_new_web_test_cleanings(
      cleaning_checklist_pk=cleaning_checklist_pk)
  return JsonResponse({'OK': True, 'example_cleaning_pk': example_cleaning.pk})


def _clear_out_old_web_test_cleanings():
  clean_co = _get_clean_co()
  work_co_rentals = ProperlyRental.objects.filter(clean_co=clean_co)

  cleaning = Cleaning.objects.filter(
      rental__properlyrental__in=work_co_rentals).first()
  while cleaning:
    if cleaning.reservation:
      delete_building(cleaning.reservation.rental.building)
    else:
      delete_cleaning(cleaning)
    cleaning = Cleaning.objects.filter(
        rental__properlyrental__in=work_co_rentals).first()
  # The clean_co_test creates this worker in the user interface.
  car_ballet = Worker.objects.filter(
      email='car@ballet.com').first()
  if car_ballet:
    car_ballet.get_child_class_instance().delete()


def _create_new_web_test_cleanings(cleaning_checklist_pk=None):
  """ Return one of them. """
  clean_co = _get_clean_co()
  _get_properly_rental('Dave\'s Dugout', clean_co)
  properly_rental = _get_properly_rental(
      'Dave\'s Donut Shop', clean_co,
      cleaning_checklist_pk=cleaning_checklist_pk)
  rental = properly_rental.rental
  three_days_ago_check_in = (now() - timedelta(days=3)).replace(
      hour=16, minute=0, second=0, microsecond=0)
  two_days_ago_check_out = (
      three_days_ago_check_in + timedelta(days=1)).replace(hour=11)
  two_days_ago_check_in = three_days_ago_check_in + timedelta(days=1)
  yesterday_check_out = two_days_ago_check_out + timedelta(days=1)
  today_check_out = two_days_ago_check_out + timedelta(days=2)
  cleaner0, cleaner1 = clean_co.workcoworker_set.all()[:2]
  get_test_cleaning(  # Canceled
      check_in=three_days_ago_check_in, check_out=two_days_ago_check_out,
      offered_to=[cleaner0], accepted_by=None,
      canceled_at=two_days_ago_check_out + timedelta(days=1), rental=rental)
  get_test_cleaning(
      check_in=two_days_ago_check_in, check_out=yesterday_check_out,
      offered_to=[cleaner0], accepted_by=cleaner0,
      completed_at=yesterday_check_out + timedelta(hours=3), rental=rental)
  tomorrow_check_in = two_days_ago_check_in + timedelta(days=3)
  two_day_check_out = yesterday_check_out + timedelta(days=3)
  get_test_cleaning(
      check_in=tomorrow_check_in, check_out=two_day_check_out, rental=rental,
      offered_to=[cleaner1], accepted_by=cleaner1)
  return get_test_cleaning(
      check_in=two_days_ago_check_in, check_out=today_check_out, rental=rental)


def _get_properly_rental(nickname, clean_co, cleaning_checklist_pk=None):
  rental = Rental.objects.filter(nickname=nickname).first()
  if not rental:
    rental = get_test_rental(nickname=nickname)
  rental.main_property_access_codes_in_order_of_use = (
      'Example main_property_access_codes_in_order_of_use')
  rental.wifi_network_name = 'Example wifi_network_name'
  rental.wifi_password = 'Example wifi_password'
  rental.extra_details = 'Example extra_details'
  rental.main_checkin_instructions_link = (
      'Example main_checkin_instructions_link')
  rental.parking_link = 'Example parking_link'
  rental.save()
  properly_rental = ProperlyRental.objects.filter(rental=rental).first()
  if not properly_rental:
    properly_rental = get_test_properly_rental(
        clean_co=clean_co, rental=rental)
  if properly_rental.clean_co != clean_co:
    properly_rental.clean_co = clean_co
    properly_rental.save()
  if properly_rental.cleaning_flat_rate != Money('95', 'USD'):
    properly_rental.cleaning_flat_rate = Money('95', 'USD')
    properly_rental.save()
  cleaning_config = CleaningConfig.objects.filter(
      properly_rental=properly_rental).first() or (
          get_test_cleaning_config(properly_rental=properly_rental))
  if cleaning_checklist_pk:
    cleaning_checklist = CleaningChecklist.objects.get(
        pk=cleaning_checklist_pk)
    cleaning_config.cleaning_checklist = cleaning_checklist
    cleaning_config.save()
  return properly_rental


def _get_clean_co():
  owner = get_web_test_user(CLEAN_CO_OWNER_USERNAME)
  clean_co = WorkCo.objects.filter(owner=owner).first()
  if not clean_co:
    clean_co = WorkCo.objects.filter(
        name='Spectacular Hassle Cleaners').first()
    if clean_co:
      clean_co.owner = owner
      clean_co.save()
    else:
      clean_co = get_test_work_co(
          owner=owner, name='Spectacular Hassle Cleaners')

  clean_co_clarance = get_web_test_user(CLEAN_CO_CLARANCE_USERNAME)
  _get_clean_co_cleaner(clean_co, 'Very Clean Clarance', clean_co_clarance)

  clean_co_bob = get_web_test_user(CLEAN_CO_BOB_USERNAME)
  _get_clean_co_cleaner(clean_co, 'Bob Slob', clean_co_bob)

  _get_clean_co_cleaner(clean_co, 'Olivia Owner', owner)
  return clean_co


def _get_clean_co_cleaner(clean_co, name, user):
  worker = user.worker_or_none
  if worker:
    worker = worker.get_child_class_instance()
    if isinstance(worker, IndependentWorker):
      raise Exception(
          'How did {} end up an IndependentWorker?'.format(user.username))
    worker.work_co = clean_co
    worker.name = name
    worker.save()
    return worker
  else:
    return get_test_work_co_worker(work_co=clean_co, name=name, base_user=user)


def get_2_maintenance_datas_for_web_test(request):
  """ This runs on the server. It returns a few test maintenance ids for your
  system test. """
  if settings.PROD:
    raise Exception('Dont create test data on production')
  _clear_out_old_web_test_maintenances()
  maintenances = _create_new_web_test_maintenances()
  return JsonResponse({'maintenances': [
      _maintenance_json(maintenance) for maintenance in maintenances]})


def _maintenance_json(maintenance):
  ticket_ids = [ticket.pk for ticket in maintenance.ticket_set.all()]
  return {'id': maintenance.pk, 'ticket_ids': ticket_ids}


def _clear_out_old_web_test_maintenances():
  for checklist in _get_4_test_checklists():
    ticket = checklist.ticket_set.first()
    while ticket:
      delete_maintenance(ticket.maintenance)
      checklist.refresh_from_db()
      ticket = checklist.ticket_set.first()
  worker = _get_independent_worker()
  for maintenance in Maintenance.objects.filter(accepted_by=worker):
    delete_maintenance(maintenance)


BEAR_TITLE = 'Bear management'
MANNEQUIN_TITLE = 'Glue the arms on the mannequins'
SCHOOL_TITLE = 'Survive junior high'
GRANDMA_TITLE = 'Become a grandmother'


def _create_new_web_test_maintenances():
  if settings.PROD:
    raise Exception('Dont create test data on prod')
  worker = _get_independent_worker()
  building = Building.objects.first()
  if not building:
    building = get_test_building()
  rentals = Rental.objects.filter(is_active=True, is_test_rental=False)[:2]
  while len(rentals) < 2:
    get_test_rental(building=building)
    rentals = Rental.objects.filter(is_active=True, is_test_rental=False)[:2]
  rental_1, rental_2 = rentals
  if not rental_1.street:
    rental_1.street = '123 4th Street'
  if not rental_1.apartment:
    rental_1.apartment = '#5'
  if not rental_2.street:
    rental_2.street = '25 Ave. A'
  if not rental_2.apartment:
    rental_2.apartment = 'Apt. 2D'
  rental_1.save()
  rental_2.save()
  for building in [rental_1.building, rental_2.building]:
    if building not in worker.buildings.all():
      worker.buildings.add(building)
  m1 = get_test_maintenance(
      rental=rental_1, offered_start_time=now() + timedelta(hours=2))
  m2 = get_test_maintenance(
      rental=rental_2, offered_start_time=now() + timedelta(hours=3))

  [cl1_1, cl1_2, cl2_1, cl2_2] = _get_4_test_checklists()
  example_image = (
      'https://res.cloudinary.com/dnsuxxqz1/image/upload/app/'
      'PXU7eTjud6Ruud8m4peG8Fdsq2jfwXVh.jpg')
  get_test_ticket(
      maintenance=m1, rental=m1.rental, title=BEAR_TITLE,
      image_url=example_image, sla=NEXT_CHECKOUT, checklist=cl1_1,
      offered_to=[worker], appendix=(
          'Not really sure how to care for bears? Check '
          'http://www.google.com'))
  get_test_ticket(
      maintenance=m1, rental=m1.rental, title=MANNEQUIN_TITLE,
      sla=NEXT_CHECKOUT, checklist=cl1_2, offered_to=[worker])
  get_test_ticket(
      maintenance=m2, rental=m2.rental, title=SCHOOL_TITLE,
      sla=NEXT_CHECKOUT, checklist=cl2_1, offered_to=[worker])
  get_test_ticket(
      maintenance=m2, rental=m2.rental, title=GRANDMA_TITLE,
      sla=NEXT_CHECKOUT, checklist=cl2_2, offered_to=[worker])
  m1.offered_to.set(m1.should_offer_to())
  m2.offered_to.set(m2.should_offer_to())
  return [m1, m2]


def _get_4_test_checklists():
  return [
      _get_test_maintenance_checklist(BEAR_TITLE, [
          'Poke the real live uncaged bear with a stick',
          'Provide the bear with a primary school education']),
      _get_test_maintenance_checklist(MANNEQUIN_TITLE, [
          'Slather glue on the arms',
          'Hold the arms to the mannequins for at least an hour']),
      _get_test_maintenance_checklist(SCHOOL_TITLE, [
          'Say it',
          'Don\'t spray it']),
      _get_test_maintenance_checklist(GRANDMA_TITLE, [
          'Fatten them up',
          'Invent a tap dance routine!'])]


def _get_test_maintenance_checklist(title, items):
  cl = MaintenanceChecklist.objects.filter(title=title).first()
  if not cl:
    cl = get_test_maintenance_checklist(
        properly_rental=None, title=title, items=items)
  return cl


def _get_independent_worker():
  user = get_web_test_user(INDEPENDENT_WORKER_USERNAME)
  if user.worker_or_none:
    return user.worker.get_child_class_instance()
  return get_test_independent_worker(
      base_user=user, name='Independent Steve', email='independent@steve.com')


def is_maintenance_complete(request, pk):
  """ This runs on the server. """
  if settings.PROD:
    raise Exception('Dont run this test against production')
  maintenance = Maintenance.objects.get(pk=pk)
  complete = maintenance.completed_at and all([
      ticket.completed_at or ticket.not_completed_at for ticket in (
          maintenance.ticket_set.all())])
  return JsonResponse({'complete': complete})


def _get_cleaning_administrator():
  return get_web_test_user(
      CLEANING_ADMINISTRATOR_USERNAME, groups=[CLEANING_ADMINISTRATOR_GROUP])


def clear_out_cleaning_checklists(request):
  if settings.PROD:
    raise Exception('Dont run this test against production')
  _get_cleaning_administrator()
  delete_all_cleaning_checklists()
  return JsonResponse({'OK': True})
