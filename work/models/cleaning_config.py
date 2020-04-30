from django.db import models
from djmoney.models.fields import MoneyField

from rentals.models import Rental
from work.models.cleaning_checklist import CleaningChecklist
from work.models.rental import ProperlyRental
from work.models.work_co import WorkCo
from util.fields import OneToOneOrNoneField


class CleaningConfigManager(models.Manager):
  def get_for_rental(self, rental):
    return self.filter(properly_rental__rental=rental).first()


class CleaningConfig(models.Model):
  properly_checklist_id = models.CharField(
      blank=True, default='', max_length=200, help_text=(
          'If the URL for the checklist is '
          'https://app.getproperly.com/#/checklists/Lcx3tM5HAB/1K6BGKUQlK/ '
          'then the properly_checklist_id is Lcx3tM5HAB'))
  cleaning_checklist = models.ForeignKey(
      CleaningChecklist, blank=True, null=True, on_delete=models.PROTECT,
      help_text=(
          'Once you set this, cleanings can happen entirely on Keys!'))
  inspection_checklist_id = models.CharField(
      max_length=200, default='', help_text=(
          'Which checklist is for cleaning inspections? Again, if the URL is '
          'https://app.getproperly.com/#/checklists/Lcx3tM5HAB/1K6BGKUQlK/ '
          'then the inspection_checklist_id is Lcx3tM5HAB'))
  cleaning_duration = models.PositiveIntegerField(default=3, help_text=(
      'In hours'))
  properly_rental = OneToOneOrNoneField(
      ProperlyRental, on_delete=models.CASCADE)
  message = models.TextField(null=True, blank=True, help_text=(
      'This goes out in the message field of every cleaning.'))
  keys_notes = models.TextField(default='', blank=True, help_text=(
      'These only show up in the cleaning config list in keys.'))

  # New fields to replace ProperlyRental. Not yet in play.
  rental_config = OneToOneOrNoneField(
      Rental, on_delete=models.CASCADE, null=True)  # Shouldn't be null.
  clean_co_config = models.ForeignKey(
      WorkCo, null=True, blank=True, on_delete=models.PROTECT, help_text=(
          'If a cleaning company is in charge of the cleanings, then they\'ll '
          'use our tools to assign cleanings, as opposed to us offering '
          'cleanings to multiple service providers.'))
  cleaning_flat_rate_config = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', null=True,
      blank=True, help_text=(
          'If a cleaning company does the cleanings, what amount do they get '
          'every time they clean this rental?'))

  objects = CleaningConfigManager()

  def save(self, *args, **kwargs):
    self.rental_config = self.properly_rental.rental
    self.clean_co_config = self.properly_rental.clean_co
    self.cleaning_flat_rate_config = self.properly_rental.cleaning_flat_rate
    super().save(*args, **kwargs)

  def __repr__(self):
    return '<CleaningConfig {}: {}>'.format(
        self.pk, self.properly_rental.rental.nickname)
