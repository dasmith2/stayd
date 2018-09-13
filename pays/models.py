""" These classes are now totally defunct and should go away,
but removing them altogether causes incomprehensible errors when
you run tests, so we'll have to wait for the next time we do
a migration compression. """
from django.db import models


class Payable(models.Model):
  email = models.CharField(blank=False, null=False, max_length=100, help_text=(
      'This email must be associated with a Paypal account.'))


class Payout(models.Model):
  pass


class PaypalPayout(Payout):
  pass
