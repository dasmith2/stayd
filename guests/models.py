import re

from django.db import models
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from util.phone import maybe_prepend_plus


class GuestManager(models.Manager):
  def get_if_exists(self, **kwargs):
    """ TODO(Dave) Yeah they do give an ID per guest. This can go
    away when the scraper goes away or gets fixed. For historical
    context...
    This is for the scraper. They don't give you an ID per guest
    so this is my best effort to notice when guests from different
    reservations are the same. Basically, full name plus any other field
    being equal is good enough. But also if there's more than one existing
    guest like that, break the tie with the number of fields that match. """
    guests = self.filter(full_name=kwargs['full_name'])
    max_guest = None
    max_guest_matches = 0
    for guest in guests:
      this_guest_matches = 0
      if guest.joined_airbnb_when == kwargs.get(
              'joined_airbnb_when', None):
        this_guest_matches += 1
      if guest.airbnb_says_theyre_from == kwargs.get(
              'airbnb_says_theyre_from', None):
        this_guest_matches += 1
      if guest.phone == kwargs.get('phone', None):
        this_guest_matches += 1
      if this_guest_matches > max_guest_matches:
        max_guest = guest
        max_guest_matches = this_guest_matches
    return max_guest


class Guest(models.Model):
  first_name = models.CharField(max_length=100, db_index=True)
  last_name = models.CharField(max_length=100, default='', db_index=True)
  full_name = models.CharField(max_length=200, db_index=True)
  joined_airbnb_when = models.DateField(null=True, blank=True)
  airbnb_says_theyre_from = models.TextField(null=True, blank=True, help_text=(
      'Not every guest has this information, but most do.'))
  phone = models.CharField(max_length=100, help_text=(
      'The primary phone number for this guest. Alternate phone numbers '
      'can be found in GuestPhoneNumber.'))
  email = models.CharField(max_length=200, default='')
  channel_id = models.CharField(max_length=100, null=True, help_text=(
      'The id given to this guest by Airbnb or Booking.com or whomever.'))

  objects = GuestManager()

  def formatted_phone(self):
    if self.phone:
      usa = re.compile(r'1(\d{3})(\d{3})(\d{4})')
      matched = usa.match(self.phone)
      if matched:
        return '({}) {}–{}'.format(*matched.groups())
    return self.phone

  def __str__(self):
    return self.full_name

  def __repr__(self):
    return '<Guest: {} ({})>'.format(self.full_name, self.pk)

  def get_name(self):
    return self.full_name or self.first_name

  def set_primary_phone(self, primary_phone):
    self.phone = primary_phone
    self.save()

  def has_phone(self, phone):
    return bool(GuestPhoneNumber.objects.filter(
        guest=self, numbers_only=GuestPhoneNumber.objects.numbers_only(phone)))


@receiver(pre_save, sender=Guest)
def pre_save(sender, instance, *args, **kwargs):
  if instance.phone:
    # I'm prepending all guesty phone numbers with a + at the time of import,
    # so this here is really just catching the case where somebody inputs an
    # international # that happens to be > 10 digits in the id verification
    # flow. Even that should be fixed up to do country codes on the client side
    # in case they do an international number that's 10 digits including
    # country code, such as mobile #s in Norway.
    instance.phone = maybe_prepend_plus(instance.phone)


@receiver(post_save, sender=Guest)
def post_save(sender, instance, *args, **kwargs):
  GuestPhoneNumber.objects.create_for_guest(instance, instance.phone)


class GuestPhoneNumberManager(models.Manager):
  def numbers_only(self, number_str):
    if number_str.__class__ is int:
      return str(number_str)
    return re.compile(r'[^\d]').sub('', number_str)

  def _find_guest_phone_numbers(self, number_str, full_name=None):
    founds = self.filter(
        numbers_only=self.numbers_only(number_str)).select_related('guest')
    if full_name:
      founds = founds.filter(guest__full_name=full_name)
    return founds

  def find_guests(self, number_str, full_name=None):
    founds = self._find_guest_phone_numbers(number_str, full_name)
    return [found.guest for found in founds]

  def find_guest(self, number_str, full_name=None):
    founds = self._find_guest_phone_numbers(number_str, full_name)
    found = founds.first()
    if found:
      return found.guest

  def create_for_guest(self, guest, phone):
    if not phone:
      return
    numbers_only = self.numbers_only(phone)
    existing = self.filter(guest=guest, numbers_only=numbers_only)
    if not existing:
      self.create(numbers_only=numbers_only, raw_string=phone, guest=guest)


class GuestPhoneNumber(models.Model):
  raw_string = models.CharField(max_length=50)
  numbers_only = models.CharField(max_length=50, db_index=True)
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)

  objects = GuestPhoneNumberManager()

  def __str__(self):
    return '{} {}'.format(self.guest, self.raw_string)


"""
HANDLE_TYPE_CHOICES = (
    ('email', 'email'),
    ('phone', 'phone'))


class BadContactInfo(models.Model):
  "" Wrong numbers and emails. Keep track of these so we only alert about
  them once. ""
  handle = models.CharField(max_length=200, help_text=(
      'The literal email or phone number thats no good.'))
  handle_type = models.CharField(max_length=10, choices=HANDLE_TYPE_CHOICES)
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)
"""
