from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.shortcuts import reverse


class WorkCo(models.Model):
  """ Turns out that assigning service providers to tasks is finicky work.
  Juggling schedules, cancelations, and so on takes up quite a bit of time. So
  now we want the ability to hire companies to source workers and assign them
  to work.
  """
  name = models.CharField(max_length=200, unique=True)
  owner = models.ForeignKey(
      User, on_delete=models.PROTECT, help_text=(
          'The company will use the username and password of this '
          'user to log in to keys to do their tasks, such as adding service '
          'providers and assigning work.'))
  alerts_email = models.CharField(max_length=100, default='', help_text=(
      'We send payments to the owners email, and alerts to this email.'))
  # This used to be on city. You'd think, hey, one city one tax rate. Turns out
  # it's not that simple. If you give taxes to a cleaning company and then they
  # simply pocket the money, perhaps because they have no idea what they're
  # doing, then those taxes are unpaid and you might be on the hook for them
  # later. Some cleaning companies do it all under the table. I hear rumors
  # that the tax rate depends on the size of the company.
  services_tax_rate = models.FloatField(default=0.0, help_text=(
      'What sales tax rate do cleaning companies charge us for cleaning '
      'services in this city as a percentage? For instance, this is 6.25 in '
      'Tempe, Arizona.'))

  def admin_url(self):
    return reverse('admin:work_workco_change', args=(self.pk,))

  def clean(self):
    if self.services_tax_rate < 0.0 or self.services_tax_rate > 100.0:
      raise ValidationError(
          'services_tax_rate should be between 0 and 100 since it\'s a '
          'percent.')
    return super().clean()

  def __repr__(self):
    return '<WorkCo {}: {}>'.format(self.pk, self.name)

  def __str__(self):
    return self.name
