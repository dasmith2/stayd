from datetime import timedelta, date

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import render

from errors.models import log_error
from nps.models.aggregate import (
    aggregate_ratings_table, GOOD_COLOR, BAD_COLOR, CAUTION_COLOR,
    get_total_sent_nps_emails, get_total_opened_nps_emails)
from nps.models.rating import (
    get_or_create_rating, ratings, ratings_table, Rating)
from rentals.models import Rental, Building, City
from rentals.tests import get_test_rental, get_test_building
from reservations.models import Reservation
from reservations.tests import get_test_reservation
from stats.models.stale import Stale
from util.admin import simple_table_page, simple_date_range_admin_page
from util.permission import is_superuser
from util.web_test_users import get_superuser
from util.timezone import now
from util.urls import dates_from_strs, nnow_from_query


def rate_us(request, channel_id):
  reservation = Reservation.objects.filter(channel_id=channel_id).first()
  if not reservation:
    return Http404('Reservation does not exist')
  problem = ''
  ask_for_comment = False
  if 'score' in request.GET:
    score = None
    try:
      score = int(request.GET['score'])
      if score < 0 or score > 10:
        problem = 'The score has to be between 0 and 10'
    except ValueError:
      problem = 'The score should be a whole number between 0 and 10'
    if not problem:
      rating = get_or_create_rating(reservation, score)
      if settings.LOCAL:
        print(
            'Stale.objects.fix() sometimes takes a long time. This should '
            'probably get fixed.')
        # This is why the nps web test sometimes hangs. Maybe I ought to just
        # delete all stale before I start.
        Stale.objects.fix()
      ask_for_comment = rating.should_get_comment()
  elif reservation.rating_or_none:
    score = reservation.rating.score

  if request.method == 'POST':
    comment = request.POST.get('comment', None)
    ask_for_comment = not comment
    if comment:
      rating = reservation.rating_or_none
      if rating:
        rating.guest_comment = comment
        rating.save()
      else:
        log_error(
            'How did a guest submit a comment without ever submitting a '
            'rating?', 'channel_id {}, comment {}'.format(channel_id, comment))
  context = {
      'problem': problem, 'score': score, 'ask_for_comment': ask_for_comment}
  return render(request, 'rate_us.html', context=context)


@login_required
@is_superuser
def nps_aggregate(request):
  total_ratings_received = Rating.objects.count()
  return simple_table_page(
      request, 'nps_aggregate', 'Net Promoter Score',
      template='nps_aggregate.html', good_color=GOOD_COLOR,
      bad_color=BAD_COLOR, caution_color=CAUTION_COLOR,
      total_ratings_received=total_ratings_received,
      total_nps_emails=get_total_sent_nps_emails(),
      total_nps_emails_opened=get_total_opened_nps_emails(),
      table=aggregate_ratings_table(nnow_from_query(request.GET)))


@login_required
@is_superuser
def nps_details(request, from_date_str='', to_date_str=''):
  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  title = 'Guests rating us on a scale from 0 to 10'
  got_ratings = ratings(from_date, to_date)
  if 'state' in request.GET:
    state = request.GET['state']
    got_ratings = got_ratings.filter(
        reservation__rental__building__city__state=state)
    title += ' in {}'.format(state)
  elif 'city' in request.GET:
    city = City.objects.get(pk=request.GET['city'])
    got_ratings = got_ratings.filter(reservation__rental__building__city=city)
    title += ' in {}, {}'.format(city.name, city.state)
  elif 'building' in request.GET:
    building = Building.objects.get(pk=request.GET['building'])
    got_ratings = got_ratings.filter(reservation__rental__building=building)
    title += ' at {}'.format(building.nickname)
  elif 'rental' in request.GET:
    rental = Rental.objects.get(pk=request.GET['rental'])
    got_ratings = got_ratings.filter(reservation__rental=rental)
    title += ' at {}'.format(rental.nickname)

  promoters = 0
  detractors = 0
  for rating in got_ratings:
    if rating.is_promoter():
      promoters += 1
    elif rating.is_detractor():
      detractors += 1
  table = ratings_table(got_ratings)
  return simple_date_range_admin_page(
      request, from_date_str, to_date_str, date.today() - timedelta(days=30),
      date.today() + timedelta(days=1), 'nps_details', title,
      template='nps_details.html', table=table,
      promoters=promoters, detractors=detractors)


def get_test_nps_channel_id(request):
  if settings.PROD:
    raise Exception('dont create test data on prod')
  building = Building.objects.filter(nickname='Dans Dugout').first()
  if not building:
    building = get_test_building(nickname='Dans Dugout')
  rental = building.rental_set.first()
  if not rental:
    rental = get_test_rental(
        building=building, nickname='Dans Dugout 25C', apartment='25C')
  rental.reservation_set.all().delete()
  # In case this is nps_test the systemtest user needs to be a super user so
  # they can see the results.
  get_superuser()

  check_in = now().replace(
      hour=16, minute=0, second=0, microsecond=0) - timedelta(days=3)
  check_out = (check_in + timedelta(days=1)).replace(hour=11)

  reservation = get_test_reservation(
      rental=rental, check_in=check_in, check_out=check_out)

  return JsonResponse({'channel_id': reservation.channel_id})
