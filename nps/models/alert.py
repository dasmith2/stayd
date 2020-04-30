from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from errors.models import Notifier
from nps.models.rating import Rating
from util.background import background
from util.fields import OneToOneOrNoneField


class Notified(models.Model):
  rating = OneToOneOrNoneField(Rating, on_delete=models.CASCADE)


@background
def notify(rating, notifier=None):
  notifier = notifier or Notifier()
  if rating.is_detractor() and not rating.notified_or_none:
    reservation = rating.reservation
    title = 'Detractor at {}'.format(reservation.rental.nickname)
    message = '{} rated us {}\n\n{}'.format(
        reservation.guest.get_name(), rating.score, reservation.admin_url())
    notifier.notify(settings.ALERT_NPS_DETRACTOR, title, message)
    Notified.objects.create(rating=rating)


@receiver(post_save, sender=Rating)
def post_save_rating(sender, instance, *args, **kwargs):
  if 'notifier' in kwargs or settings.PROD:
    notify(instance, notifier=kwargs.get('notifier', None))
