from datetime import datetime

from django.utils.timezone import make_aware

from guests.tests import get_test_guest
from listings.tests import get_test_listing
from reservations.models import Reservation


def get_test_reservation(create, **kwargs):
  guest = get_test_guest(create, **kwargs)
  listing = get_test_listing(create, **kwargs)
  reservation = Reservation(
      channel_reservation_id=kwargs.get('channel_reservation_id', '12345678'),
      guest=kwargs.get('guest', guest),
      check_in=kwargs.get('check_in', make_aware(datetime(2018, 3, 1, 15))),
      check_out=kwargs.get('check_out', make_aware(datetime(2018, 3, 3, 11))),
      booked_at=kwargs.get('booked_at', make_aware(datetime(2018, 2, 25, 15))),
      planned_arrival=kwargs.get('planned_arrival', None),
      id_verified=kwargs.get('id_verified', False),
      listing=kwargs.get('listing', listing),
      price_per_night=kwargs.get('price_per_night', 125),
      night_count=kwargs.get('night_count', 2),
      total_payin=kwargs.get('total_payin', 340),
      is_paid_in=kwargs.get('is_paid_in', True),
      security_deposit=kwargs.get('security_deposit', None),
      auto_communicate=kwargs.get('auto_communicate', True))
  if create:
    reservation.save()
  return reservation
