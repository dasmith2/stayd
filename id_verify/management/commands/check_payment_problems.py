from commands.stayd_command import StaydCommand
from reservations.syncer import ReservationManagerIsDown
from reservations.models import Reservation


class Command(StaydCommand):
  help = (
      'Guesty should send us a reservation.updated webhook when a payment '
      'comes in for that Reservation, but they don\'t. This hourly task '
      'will hopefully cut down on the cases where the user does make a '
      'successful payment, we didn\'t hear about it, and we call them up '
      'bugging them about it. Now this also helps with sending out the '
      'confirmation email.')

  def run(self, verbose):
    for reservation in Reservation.objects.expecting_payments():
      try:
        reservation.sync()
      except ReservationManagerIsDown:
        pass

  def name(self):
    return 'check_payment_problems'
