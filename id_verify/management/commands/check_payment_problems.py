from commands.stayd_command import StaydCommand
from reservations.models import Reservation


class Command(StaydCommand):
  help = (
      'Guesty should send us a reservation.updated webhook when a payment '
      'comes in for that Reservation, but they don\'t. This hourly task '
      'will hopefully cut down on the cases where the user does make a '
      'successful payment, we didn\'t hear about it, and we call them up '
      'bugging them about it.')

  def run(self, verbose):
    for reservation in Reservation.objects.payment_problems():
      reservation.sync()

  def name(self):
    return 'resize_and_clean_up_id_images'
