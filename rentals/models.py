import moneyed
import pytz
from djmoney.money import Money
from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import make_aware, is_aware
from djmoney.models.fields import MoneyField


class RentalManager(models.Manager):
  def city_names(self):
    django_cities = self.filter(
        is_active=True).order_by().values('city').distinct()
    return list(sorted(filter(None, [city['city'] for city in django_cities])))

  def get_owners(self):
    owner_ids = Rental.objects.order_by(
        'owner_id').values_list('owner').distinct()
    return User.objects.filter(pk__in=owner_ids)


class Rental(models.Model):
  """ A rental unit. Could be an apartment, or house, whatever, it's available
  for short term rental. It can be listed on multiple channels such as Airbnb.
  """
  airbnb_address_scrape = models.TextField(help_text=(
      'This is the address as scraped off Airbnb verbatim. Just... '
      'hang onto this field to make our lives easier for now.'))
  city = models.CharField(max_length=200, default='')
  time_zone = models.CharField(
      max_length=40, default='US/Eastern', choices=(
          (tz, tz) for tz in pytz.all_timezones))
  currency = models.CharField(
      max_length=3, default='USD', choices=sorted(
          ((c, c) for c in moneyed.CURRENCIES.keys())))
  accommodates = models.PositiveIntegerField(help_text=(
      'How many people can sleep here.'))
  bathrooms = models.PositiveIntegerField()
  bedrooms = models.PositiveIntegerField()
  property_type = models.CharField(max_length=50, help_text=(
      'Keep this vague until I know what the exhaustive enumeration '
      'of possible values is.'))
  room_type = models.CharField(max_length=50, help_text=(
      'Keep this vague until I know what the exhaustive enumeration '
      'of possible values is.'))
  owner = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
  nickname = models.CharField(max_length=250, default='')
  is_active = models.BooleanField(default=False, help_text=(
      'All kinds of rentals end up in the database for various reasons. We '
      'only want the, like, really active ones to show up in reports though.'))
  # Whew, ok this list happens a pile of times. Tight coupling, I know.
  # It was a choice between explicit and magic.
  # * rentals/tests.py get_test_rental
  # * It's also in guesty/api.py sync_rental because they have to be copied
  #   from somewhere
  # * guesty/custom_fields.py as a list of custom fields because that's where
  #   these all come from
  # * guesty/api_examples.py RENTAL and
  # * guesty/test_api.py test_sync_rentals to test loading these values.
  # * guest_messages/template_tags.py get_template_params_for_reservation
  #   because these were mainly brought in to put in emails
  # * guest_messages/tests.py test_get_message_string because I gotta verify
  #   those emails.
  # * guest_messages/templates/template_tags.html to let Marc know what fields
  #   he has to work with.
  main_checkin_instructions_link = models.CharField(
      max_length=250, default='')
  main_property_access_codes_in_order_of_use = models.CharField(
      max_length=250, default='')
  master_access_code_building_door_electronic_lock = models.CharField(
      max_length=250, default='')
  master_access_code_apartment_door_electronic_lock = models.CharField(
      max_length=250, default='')
  wifi_network_name = models.CharField(
      max_length=250, default='')
  wifi_password = models.CharField(
      max_length=250, default='')
  building_trash_instructions = models.TextField(
      default='')
  link_to_property_page_in_helpdocs = models.CharField(
      max_length=250, default='')
  google_maps_link = models.CharField(
      max_length=250, default='')
  departure_check_list = models.TextField(
      max_length=250, default='')
  local_bag_storage_info = models.TextField(
      default='')
  local_bag_storage_link = models.TextField(
      default='')
  parking_link = models.CharField(
      max_length=250, default='')
  public_transportation_link = models.CharField(
      max_length=250, default='')
  local_recommendations_link = models.CharField(
      max_length=250, default='')
  walking_to_nearest_path_stations = models.TextField(
      max_length=250, default='')
  parking_suggestions_no_links = models.TextField(
      default='')
  public_transport_no_link = models.TextField(
      default='')
  walk_time_to_nearest_train = models.CharField(
      max_length=250, default='')
  laundry_info = models.TextField(
      default='')
  online_store_available = models.BooleanField(
      default=False)

  objects = RentalManager()

  def get_nickname(self):
    return self.nickname or self.airbnb_address_scrape

  class Meta:
    ordering = ['airbnb_address_scrape']

  def set_timezone(self, dt):
    """ Return the given datetime with the timezone set to the timezone of this
    rental. """
    if is_aware(dt):
      return dt
    return make_aware(dt, pytz.timezone(self.time_zone))

  def set_currency(self, m):
    """ Return the given money with the currency set to the currency of this
    rental. """
    if m.__class__ is Money:
      return Money(m.amount, self.currency)
    return Money(m, self.currency)

  def pro_rated_rent(self, from_date, to_date):
    """ to_date is excluded. This runs a query due to self.monthlyexpense_set... so
    as it stands, don't use this to pull down the pro-rated rent of every day
    in a year or anything like that. """
    last_lease = None
    days_left = (to_date - from_date).days
    rent = Money(0, 'USD')
    for lease in self.monthlyexpense_set.order_by('-start_date'):
      if lease.start_date >= to_date:
        continue
      measure_to_date = to_date
      if last_lease:
        measure_to_date = last_lease.start_date
      last_lease = lease
      lease_days = (measure_to_date - lease.start_date).days
      daily_amount = lease.daily_amount()
      if lease_days < days_left:
        rent += lease_days * daily_amount
        days_left -= lease_days
      else:
        rent += days_left * daily_amount
        break
    return rent

  def __str__(self):
    return self.airbnb_address_scrape

  def __repr__(self):
    return 'Rental({})'.format(self.airbnb_address_scrape)


RENT = 'Rent'
MONTHLY_EXPENSE_KINDS = (
    (RENT, RENT),)


class MonthlyExpense(models.Model):
  """ This started as a model to keep track of leases. This class makes the
  most sense when there is at most 1 of them per (rental, month, kind).
  If one lease starts January 1st, and another lease starts February 15th, then
  I make the assumption that you pay the January price pro rated for the first
  14 days of February, and the February lease pro rated for the remaining days.
  So don't put 2 gas bills in the same month for the same rental in here. It'll
  do pro rating stuff you don't expect. Rather just do one entry on the first
  of the month with the sum of both bills. """
  rental = models.ForeignKey(Rental, on_delete=models.CASCADE)
  start_date = models.DateField()
  monthly_amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ')
  kind = models.CharField(choices=MONTHLY_EXPENSE_KINDS, max_length=20)

  def daily_amount(self):
    return self.monthly_amount * 12 / 365

  def __repr__(self):
    return '{}({}, {})'.format(self.kind, self.start_date, self.monthly_rent)

  class Meta:
    ordering = ('rental', 'start_date', 'kind')
