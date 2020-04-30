from django.db import models
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.shortcuts import reverse

from work.models.work_co import WorkCo
from work.models.work_type import WorkType, CLEANER
from work.models.worker import Worker


class WorkCoWorker(Worker):
  work_co = models.ForeignKey(WorkCo, on_delete=models.CASCADE)
  # So this is, like, active_by_us
  active = models.BooleanField(default=True, help_text=(
      'We use this to deactivate service providers who arent up to our '
      'standards. This must be on in order for the service provider to be '
      'available in the cleaning company\'s dashboard.'))
  active_by_cleaning_company = models.BooleanField(
      default=True, help_text=(
          'The cleaning companies want a mechanism to remove old service '
          'providers from their user interface entirely.'))
  internal_notes = models.TextField(default='', blank=True, help_text=(
      'These are only visible inside Howard. If you inactivate a worker, '
      'you should probably explain why here.'))

  def clean_hihoward_com_edit_url(self):
    return reverse('cleaner', kwargs={'pk': self.pk})

  def get_payment_email(self):
    return self.work_co.owner.email

  def get_hour_min(self):
    return self.work_co.hour_min

  def get_work_co(self):
    return self.work_co

  def __repr__(self):
    return '<(WorkCo)Worker {}: {} {}>'.format(
        self.pk, self.name, self.work_co)

  class Meta:
    ordering = ('name',)


@receiver(post_save, sender=WorkCoWorker)
def post_save_work_co_worker(sender, instance, *args, **kwargs):
  """ This is so we get cleaning inspection stuff automatically on all
  WorkCoWorkers. """
  if not instance.is_cleaner():
    instance.work_types.add(WorkType.objects.get(name=CLEANER))
