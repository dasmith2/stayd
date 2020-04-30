""" Probably the biggest regret of my life was picking the term Rental instead
of Unit.

Combo rentals don't actually exist in real life. They're virtual combinations
of existing rentals. Combo rentals have a non-empty is_combo_of property
containing 2 or more atom rentals. By atom rental I simply mean its is_combo_of
IS empty, a.k.a. it represents a single actual apartment or whatever. The point
of combo rentals is, sometimes people wanna book a reservation for, like, 50
people all at once in connected rentals. """
from calendar import monthrange
from datetime import datetime, date

import moneyed
import pytz
from djmoney.money import Money
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils.timezone import make_aware, is_aware
from djmoney.models.fields import MoneyField

from util.timezone import tz_dt_to_tz_dt, now


class SMSChannel(models.Model):
  name = models.CharField(max_length=100)
  identifier = models.CharField(max_length=100)

  def __repr__(self):
    return '<SMSChannel {}: {} {}>'.format(self.pk, self.name, self.identifier)

  def __str__(self):
    return self.name


TIMEZONE_CHOICES = ((tz, tz) for tz in pytz.all_timezones)


class City(models.Model):
  name = models.CharField(
      max_length=200, help_text='Guesty overwrites this field.')
  # There are cities with the same name in different states, so that unique
  # constraint on name is incorrect. This state field is the first step to
  # fixing that.
  state = models.CharField(max_length=200, default='', blank=True)
  country = models.CharField(
      max_length=200, help_text='Guesty overwrites this field.', default='')

  def __repr__(self):
    return '<City {}: {}>'.format(self.pk, self.name)

  def __str__(self):
    if self.state:
      return '{}, {}'.format(self.name, self.state)
    return self.name

  class Meta:
    unique_together = ('name', 'state')


def all_city_names():
  return sorted([city.name for city in City.objects.all()])


class Building(models.Model):
  city = models.ForeignKey(City, on_delete=models.PROTECT)
  street = models.CharField(
      max_length=200, help_text='Guesty overwrites this field.', default='')
  zipcode = models.CharField(
      max_length=200, help_text='Guesty overwrites this field.', default='')
  time_zone = models.CharField(
      max_length=40, default='US/Eastern', choices=TIMEZONE_CHOICES,
      help_text='Guesty overwrites this field.')
  owner = models.ForeignKey(User, null=True, on_delete=models.PROTECT)
  nickname = models.CharField(max_length=250, unique=True)
  is_active = models.BooleanField(default=False, help_text=(
      'All kinds of rentals end up in the database for various reasons. We '
      'only want the, like, really active ones to show up in reports though.'))
  currency = models.CharField(
      max_length=3, default='USD', choices=sorted(
          ((c, c) for c in moneyed.CURRENCIES.keys())))
  alerts_email = models.CharField(
      max_length=100, default=settings.DEFAULT_BUILDING_ALERT_EMAIL)
  sms_staff_from = models.ForeignKey(
      SMSChannel, null=True, blank=True, on_delete=models.PROTECT, help_text=(
          'Where should we send staff SMSs from?'))
  latitude = models.DecimalField(
      decimal_places=6, max_digits=9, null=True, blank=True)
  longitude = models.DecimalField(
      decimal_places=6, max_digits=9, null=True, blank=True)
  background_check_guests = models.BooleanField(default=False, help_text=(
      'Are we contractually obligated to run a criminal background check '
      'on guests before we let them stay in this building?'))

  def city_nickname(self):
    return '{}: {}'.format(self.city, self.nickname)

  def get_nickname(self):
    return self.nickname or self.street

  def get_owner_name(self):
    owner = self.owner
    if not owner:
      return ''
    return ' '.join(
        filter(None, [owner.first_name, owner.last_name, owner.email]))

  def nickname_aware_location(self):
    if self.nickname:
      return '{}, {}'.format(self.street, self.city)
    else:
      # In this case it's using self.street for the nickname
      return self.city.name

  def set_timezone(self, dt):
    """ Return the given datetime with the timezone set to the timezone of this
    rental. """
    if is_aware(dt):
      return tz_dt_to_tz_dt(dt, self.time_zone)
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
    if any([
        self.street, self.city.name, self.city.state, self.zipcode,
        self.city.country]):
      return '{}, {}, {} {}, {}'.format(
          self.street, self.city.name, self.city.state, self.zipcode,
          self.city.country)
    return 'Guesty hasn\'t synced the addres for "{}" yet'.format(
        self.nickname)

  def __str__(self):
    return '{}: {}'.format(self.city, self.get_nickname())

  def __repr__(self):
    return '<Building {}: {}>'.format(self.pk, self.get_nickname())

  class Meta:
    ordering = ['city__name', 'nickname']


class RentalManager(models.Manager):
  def live_atoms(self):
    """ This is used by new ticket forms. """
    return self.filter(
        is_test_rental=False, is_active=True, building__is_active=True,
        combo_unit_description='')

  def get_owners(self):
    owner_ids = Rental.objects.order_by(
        'building__owner_id').values_list('building__owner').distinct()
    return User.objects.filter(pk__in=owner_ids).order_by(
        'first_name', 'last_name', 'email')


class Amenity(models.Model):
  """ These are being tracked for the iPhone app. """
  name = models.CharField(max_length=200, help_text=(
      'TV, Air conditioning, Wireless Internet, that kind of thing.'))


# These are copied directly from guesty, for what that's worth.
BOOKED = 'booked'
UNAVAILABLE = 'unavailable'
AVAILABLE = 'available'


class Rental(models.Model):
  """ A rental unit. Could be an apartment, or house, whatever, it's available
  for short term rental. It can be listed on multiple channels such as Airbnb.
  """
  building = models.ForeignKey(
      Building, on_delete=models.PROTECT, help_text=(
          'Every Rental is in a building. If its a standalone rental, easy, '
          'its just the only Rental in the building.'))
  full_address = models.TextField(help_text=(
      'This is the address as scraped off Airbnb verbatim. Just... '
      'hang onto this field to make our lives easier for now.'))
  # Whoops, this is in building too. NBD but ideally we'd get rid of this.
  street = models.CharField(
      max_length=100, default='', blank=True,
      help_text=(
          'Full address is me.street me.apartment, me.building.city.name'))
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
  nickname = models.CharField(max_length=250, default='', unique=True)
  is_active = models.BooleanField(default=False, help_text=(
      'All kinds of rentals end up in the database for various reasons. We '
      'only want the, like, really active ones to show up in reports though. '
      'Nobody is totally clear on where this field comes from, but it may '
      'come all the way from Airbnb and such.'))
  reports_start_date = models.DateField(
      default=date(2018, 1, 1), help_text=(
          'When did this one come online and we should start reporting '
          'available occupancy for instance?'))
  reports_end_date = models.DateField(
      blank=True, null=True, help_text='When did this rental go offline?')
  maintenance_purposes_only = models.BooleanField(default=False, help_text=(
      'Check this box if no reservations will ever happen at this rental '
      'and you want to be able to schedule regular maintenance here.'))
  neighborhood = models.CharField(
      max_length=200, null=True, blank=True, help_text=(
          'This is filled in manually. You probably want to use '
          'get_neighborhood which defaults to city if this isnt filled in.'))
  # You aren't allowed to have a combo unit of combo units. Django doesn't
  # really have a great spot to enforce that kind of requirement on a
  # ManyToManyField, but at least it's enforced in the admin in the clean
  # method of the RentalForm, and by not even showing combo rentals as choices
  # in the is_combo_of queryset.
  is_combo_of = models.ManyToManyField(
      'self', symmetrical=False, blank=True, help_text=(
          'Why rent units 1 and 2 separately for $100 a night each when you '
          'could rent them together for $250?'))
  combo_unit_description = models.TextField(default='', help_text=(
      'Dont set this manually. Its just a cache of combo unit details so the '
      'admin can run fast.'))
  cleaning_fee = MoneyField(  # For the iPhone app
      max_digits=10, decimal_places=2, default_currency='XYZ', blank=True,
      null=True, help_text=(
          'How much per reservation do we charge to clean the place?'))
  extra_guest_fee = MoneyField(  # iPhone app
      max_digits=10, decimal_places=2, default_currency='XYZ', blank=True,
      null=True, help_text=(
          'How much do we charge per extra guest to stay at this place?'))
  guests_before_fee = models.PositiveIntegerField(  # iPhone app
      default=1, help_text=(
          'How many guests can you have before we start charging the extra '
          'guest fee?'))
  amenities = models.ManyToManyField(Amenity)  # iPhone app

  bed_count = models.PositiveIntegerField(blank=True, null=True)
  brief_description = models.TextField(blank=True, null=True)

  """
  Whew, ok this list happens a pile of times. Tight coupling, I know. It was
  a choice between explicit and magic. These are custom Listing fields from
  Guesty.
  1. rentals/tests.py get_test_rental
  2. It's also in guesty/guesty.py _get_unsaved_rental_object_from_data because
     they have to be copied from somewhere
  3. guesty/custom_fields.py as a list of custom fields because
     that's where these all come from
  4. guesty/api_examples.py RENTAL and
  5. guesty/test_guesty.py test_sync_rentals to test loading these values.
  6. guest_messages/template_tags.py get_template_params_for_reservation
     because these were mainly brought in to put in emails
  7. guest_messages/tests.py test_get_message_string because I gotta verify
     those emails.
  8. guest_messages/templates/template_tags.html to let Marc know what fields
     he has to work with. Usually this is just adding to SIMPLE_TEMPLATE_TAGS
     in guest_messages/views.py
  """
  main_checkin_instructions_link = models.TextField(
      default='')
  main_property_access_codes_in_order_of_use = models.TextField(
      default='')
  master_access_code_building_door_electronic_lock = models.TextField(
      default='')
  master_access_code_apartment_door_electronic_lock = models.TextField(
      default='')
  backup_check_in_codes = models.TextField(
      default='')
  backup_check_in_instructions_link = models.TextField(
      default='')
  wifi_network_name = models.TextField(
      default='')
  wifi_password = models.TextField(
      default='')
  building_trash_instructions = models.TextField(
      default='')
  link_to_property_page_in_helpdocs = models.TextField(
      default='')
  google_maps_link = models.TextField(
      default='')
  departure_check_list = models.TextField(
      default='')
  local_bag_storage_info = models.TextField(
      default='')
  local_bag_storage_link = models.TextField(
      default='')
  parking_link = models.TextField(
      default='')
  public_transportation_link = models.TextField(
      default='')
  local_recommendations_link = models.TextField(
      default='')
  walking_to_nearest_path_stations = models.TextField(
      default='')
  parking_suggestions_no_links = models.TextField(
      default='')
  public_transport_no_link = models.TextField(
      default='')
  walk_time_to_nearest_train = models.TextField(
      default='')
  laundry_info = models.TextField(
      default='')
  online_store_available = models.BooleanField(
      default=False)
  is_test_rental = models.BooleanField(
      default=False, help_text='Dont include these in reports')
  extra_details = models.TextField(
      default='')
  leave_the_keys = models.TextField(
      default='', help_text='A reminder to guests as theyre leaving')

  objects = RentalManager()

  def todays_checkout_time(self, nnow=None):
    nnow = nnow or now()
    return self.building.set_timezone(
        datetime(nnow.year, nnow.month, nnow.day, 11, 00))

  def get_availability(self, night, api=None):
    if not self.guestyrental_or_none:
      raise Exception(
          'I only know how to check availability on rentals in Guesty, which '
          'this rental isnt.')
    return self.guestyrental_or_none.get_availability(night, api=api)

  def is_combo_rental(self):
    return bool(self.combo_unit_description)

  def get_rentals(self):
    if self.is_combo_rental():
      return self.is_combo_of.all()
    return [self]

  def get_neighborhood(self):
    return self.neighborhood or self.city.name

  def get_nickname(self):
    return self.nickname or self.full_address

  def get_apartment(self):
    return self.apartment or self.get_nickname()

  def block(self, night, reason, api=None):
    self.guestyrental.block(night, reason, api)

  def unblock(self, night, api=None):
    self.guestyrental.unblock(night, api)

  def is_blocked(self, night, api=None):
    return self.guestyrental.is_blocked(night, api)

  def set_combo_unit_description(self):
    combo_of = self.is_combo_of.all().order_by('apartment', 'nickname', 'pk')
    parts = []
    for rental in combo_of:
      parts.append(rental.apartment or rental.nickname or str(rental.pk))
    combo_unit_description = ', '.join(parts)
    if self.combo_unit_description != combo_unit_description:
      self.combo_unit_description = combo_unit_description
      self.save()

  def sync(self):
    from guesty.guesty import Guesty
    sync = Guesty()
    sync.sync_rental(sync.api.get_one(Rental, self.guestyrental.guesty_id))
    self.refresh_from_db()

  class Meta:
    ordering = ['building__city', 'building__nickname', 'apartment']

  def __str__(self):
    return self.nickname or self.full_address

  def __repr__(self):
    return '<Rental {}: {}>'.format(self.pk, self.nickname)


@receiver(m2m_changed, sender=Rental.is_combo_of.through)
def post_m2m_changed(sender, instance, *args, **kwargs):
  instance.set_combo_unit_description()


class RentalPhoto(models.Model):
  rental = models.ForeignKey(Rental, on_delete=models.CASCADE)
  thumbnail_url = models.TextField(null=True, blank=True)
  regular_url = models.TextField(null=True, blank=True)
  large_url = models.TextField(null=True, blank=True)
  original_url = models.TextField(null=True, blank=True)


RENT = 'Rent'
INSURANCE = 'Insurance'
MONTHLY_EXPENSE_KINDS = (
    (RENT, RENT),
    (INSURANCE, INSURANCE))


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

  def daily_amount(self, on):
    return self.monthly_amount / monthrange(on.year, on.month)[1]

  def __repr__(self):
    return '{}({}, {})'.format(self.kind, self.start_date, self.monthly_amount)

  class Meta:
    ordering = ('rental', 'start_date')
    unique_together = (('rental', 'start_date', 'monthly_amount', 'kind'),)
