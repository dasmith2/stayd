from django.db import models


class GuestManager(models.Manager):
  def get_if_exists(self, **kwargs):
    """ TODO(Dave) Yeah they do give an ID per guest.
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
  full_name = models.TextField(db_index=True, help_text=(
      'At the moment this is scraped verbatim off of Airbnb.'))
  joined_airbnb_when = models.DateField()
  airbnb_says_theyre_from = models.TextField()
  phone = models.CharField(max_length=50)

  objects = GuestManager()

  def __str__(self):
    return self.full_name

  def __repr__(self):
    return '<Guest: {} ({})>'.format(self.full_name, self.pk)
