import moneyed
import pytz
from djmoney.money import Money
from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import make_aware, is_aware
from djmoney.models.fields import MoneyField


class BuildingManager(models.Manager):
  def city_names(self):
    django_cities = self.filter(
        is_active=True).order_by().values('city').distinct()
    return list(sorted(filter(None, [city['city'] for city in django_cities])))


TIMEZONE_CHOICES = ((tz, tz) for tz in pytz.all_timezones)


class Building(models.Model):
  city = models.CharField(
      max_length=200, help_text='Guesty overwrites this field.', default='')
  country = models.CharField(
      max_length=200, help_text='Guesty overwrites this field.', default='')
  state = models.CharField(
      max_length=200, help_text='Guesty overwrites this field.', default='')
  street = models.CharField(
      max_length=200, help_text='Guesty overwrites this field.', default='')
  zipcode = models.CharField(
      max_length=200, help_text='Guesty overwrites this field.', default='')
  time_zone = models.CharField(
      max_length=40, default='US/Eastern', choices=TIMEZONE_CHOICES,
      help_text='Guesty overwrites this field.')
  owner = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
  nickname = models.CharField(max_length=250, default='')
  is_active = models.BooleanField(default=False, help_text=(
      'All kinds of rentals end up in the database for various reasons. We '
      'only want the, like, really active ones to show up in reports though.'))
  currency = models.CharField(
      max_length=3, default='USD', choices=sorted(
          ((c, c) for c in moneyed.CURRENCIES.keys())))

  objects = BuildingManager()

  def get_nickname(self):
    return self.nickname or self.street

  def nickname_aware_location(self):
    if self.nickname:
      return '{}, {}'.format(self.street, self.city)
    else:
      # In this case it's using self.street for the nickname
      return self.city

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

  def address(self):
    """ When you create a new building, guesty hasn't synced the addres yet,
    but you are prompted for a nickname, so that should exist if the address
    doesn't. """
    if any([self.street, self.city, self.state, self.zipcode, self.country]):
      return '{}, {}, {} {}, {}'.format(
          self.street, self.city, self.state, self.zipcode, self.country)
    return 'Guesty hasn\'t synced the addres for "{}" yet'.format(
        self.nickname)

  def __str__(self):
    if self.nickname:
      return '{}: {}'.format(self.nickname, self.address())
    return self.address()

  def __repr__(self):
    return 'Building({})'.format(self)

  class Meta:
    ordering = ['street', 'city', 'state', 'zipcode']


class RentalManager(models.Manager):
  def get_owners(self):
    owner_ids = Rental.objects.order_by(
        'building__owner_id').values_list('building__owner').distinct()
    return User.objects.filter(pk__in=owner_ids)


class Rental(models.Model):
  """ A rental unit. Could be an apartment, or house, whatever, it's available
  for short term rental. It can be listed on multiple channels such as Airbnb.
  """
  building = models.ForeignKey(
      Building, on_delete=models.CASCADE, help_text=(
          'Every Rental is in a building. If its a standalone rental, easy, '
          'its just the only Rental in the building.'))
  full_address = models.TextField(help_text=(
      'This is the address as scraped off Airbnb verbatim. Just... '
      'hang onto this field to make our lives easier for now.'))
  apartment = models.CharField(
      max_length=100, blank=True, null=True, help_text='Apartment number')
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
    return self.nickname or self.full_address

  class Meta:
    ordering = ['full_address']

  def pro_rated_rent(self, from_date, to_date):
    from stats.models.stats import DAY
    from stats.models.computer import compute_stats
    from stats.models.getter import StatsGetter
    days = compute_stats(
        from_date, to_date, DAY, rental_id=self.pk)
    total = StatsGetter().sum_statses(days)
    return Money(total.rent, self.building.currency)

  def __str__(self):
    return self.full_address

  def __repr__(self):
    return 'Rental({})'.format(self.full_address)


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
    return '{}({}, {})'.format(self.kind, self.start_date, self.monthly_amount)

  class Meta:
    ordering = ('rental', 'start_date', 'kind')
    unique_together = (('rental', 'start_date', 'monthly_amount', 'kind'),)
