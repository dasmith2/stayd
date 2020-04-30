""" This is basically for properly ids associated with rentals and
reservations. It's bookkeeping, really. Not much interesting happens here.
The only interesting thing is checklist_id and cleaning_duration which ought
to be in work.models.jobs.CleaningConfig or something. """

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from djmoney.models.fields import MoneyField

from errors.models import log_error
from work.api import API
from work.models.work_co import WorkCo
from rentals.models import Rental
from util.background import background
from util.fields import OneToOneOrNoneField
from util.signals import post_sync
from util.timezone import tz_dt_to_tz_dt


def properly_datetime_format(dt):
  return tz_dt_to_tz_dt(dt, 'UTC').isoformat().replace('+00:00', 'Z')


class ProperlyRentalManager(models.Manager):
  def get_source_property_id(self, rental):
    properly_rental = self.filter(rental=rental).first()
    if properly_rental:
      return properly_rental.get_source_property_id()
    log_error('{} needs a properly rental'.format(rental.nickname))

  def get_for_rental(self, rental):
    return self.filter(rental=rental).first()


class ProperlyRental(models.Model):
  rental = OneToOneOrNoneField(Rental, on_delete=models.CASCADE)
  # One time, somebody accidentally configured 2 properly rentals with the same
  # properly rental id so the bookings for both rentals tried to go under the
  # same rental in properly, which didn't show the overlapping bookings. So now
  # unique=True.
  properly_property_id = models.CharField(
      max_length=200, null=True, blank=True, unique=True, help_text=(
          'If the URL for the property is '
          'https://app.getproperly.com/#/properties/Dzb3DEE0zD/checklists '
          'then this is Dzb3DEE0zD'))
  source_property_id = models.CharField(
      max_length=100, null=True, blank=True, unique=True, help_text=(
          'Dont set this manually. The source_property_id must be set via the '
          'property.update command so it can populate the sourcePropertyId '
          'field of the jobRequest.create command.'))
  clean_co = models.ForeignKey(
      WorkCo, null=True, blank=True, on_delete=models.PROTECT, help_text=(
          'If a cleaning company is in charge of the cleanings, then they\'ll '
          'use our tools to assign cleanings, as opposed to us offering '
          'cleanings to multiple service providers.'))
  cleaning_flat_rate = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', null=True,
      blank=True, help_text=(
          'If a cleaning company does the cleanings, what amount do they get '
          'every time they clean this rental?'))

  objects = ProperlyRentalManager()

  def save(self, *args, **kwargs):
    if self.cleaningconfig_or_none:
      self.cleaningconfig.rental_config = self.rental
      self.cleaningconfig.clean_co_config = self.clean_co
      self.cleaningconfig.cleaning_flat_rate_config = self.cleaning_flat_rate
      self.cleaningconfig.save()
    super().save(*args, **kwargs)

  class Meta:
    ordering = ('rental__building__city', 'rental__building__nickname')

  def __repr__(self):
    return '<ProperlyRental {}: {}>'.format(self.pk, self.rental.nickname)

  def __str__(self):
    return '{}: {}'.format(self.rental.building.city, self.rental.nickname)

  def _get_desired_source_property_id(self):
    return self.properly_property_id

  def set_source_property_id(self, api=API()):
    got = api.property_update({
        'propertyId': self.properly_property_id,
        'changes': {'sourceId': self._get_desired_source_property_id()}})
    self.source_property_id = self._get_desired_source_property_id()
    self.save()
    return got

  def get_source_property_id(self, api=API()):
    if not self.properly_property_id:
      raise Exception(
          'You have to set the properly_property_id before you can set the '
          'source_property_id')
    if self._get_desired_source_property_id() != self.source_property_id and (
        settings.PROD or settings.TEST):
      self.set_source_property_id(api=api)
    return self.source_property_id

  def is_configured(self):
    return bool(self.source_property_id)


@receiver(post_sync, sender=Rental)
def post_rental_sync(sender, instance, *args, **kwargs):
  ProperlyRental.objects.get_or_create(rental=instance)


@receiver(post_save, sender=ProperlyRental)
def post_properly_rental_save(sender, instance, *args, **kwargs):
  if instance.properly_property_id and (
      instance.properly_property_id != instance.source_property_id):
    _set_properly_rental_source_property_id(instance)
  elif instance.source_property_id and not instance.properly_property_id:
    instance.source_property_id = instance.properly_property_id
    instance.save()


@background
def _set_properly_rental_source_property_id(properly_rental):
  properly_rental.get_source_property_id()
