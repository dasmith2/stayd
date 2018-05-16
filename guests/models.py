import re

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


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
  first_name = models.CharField(max_length=100)
  full_name = models.CharField(max_length=200)
  joined_airbnb_when = models.DateField(null=True, blank=True)
  airbnb_says_theyre_from = models.TextField(null=True, blank=True, help_text=(
      'Not every guest has this information, but most do.'))
  phone = models.CharField(max_length=100, help_text=(
      'The canonical phone number for this guest. Alternate phone numbers '
      'can be found in GuestPhoneNumber.'))
  channel_id = models.CharField(max_length=100, null=True, help_text=(
      'The id given to this guest by Airbnb or Booking.com or whomever.'))

  objects = GuestManager()

  @receiver(post_save)
  def post_save(sender, instance, *args, **kwargs):
    if instance.__class__ is Guest:
      GuestPhoneNumber.objects.create_for_guest(instance)

  def __str__(self):
    return self.full_name

  def __repr__(self):
    return '<Guest: {} ({})>'.format(self.full_name, self.pk)


class GuestPhoneNumberManager(models.Manager):
  def numbers_only(self, number_str):
    if number_str.__class__ is int:
      return str(number_str)
    return re.compile(r'[^\d]').sub('', number_str)

  def find(self, number_str):
    return self.filter(numbers_only=self.numbers_only(number_str)).first()

  def create_for_guest(self, guest):
    existing = self.filter(guest=guest)
    existing_nums_only = [g.numbers_only for g in existing]
    for n in guest.phone.split(','):
      numbers_only = self.numbers_only(n)
      raw_string = n.strip()
      if numbers_only not in existing_nums_only:
        self.create(
            numbers_only=numbers_only, raw_string=raw_string, guest=guest)


class GuestPhoneNumber(models.Model):
  raw_string = models.CharField(max_length=50)
  numbers_only = models.CharField(max_length=50)
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)

  objects = GuestPhoneNumberManager()

  def __str__(self):
    return '{} {}'.format(self.guest, self.raw_string)
