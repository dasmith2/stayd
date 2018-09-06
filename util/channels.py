"""
Is guesty giving you a weird name for the channel, and you want to put
something in place so our database has something readable?
get_channel_from_source in guesty.api.GuestySync has all those.
"""

AIRBNB = 'Airbnb'
BOOKINGCOM = 'Booking.com'
HOMEAWAY = 'HomeAway'
STAYD = 'reservations.stayd.com'
RENTALS_UNITED = 'RentalsUnited'
ONLY_APARTMENTS = 'OnlyApartments'

CHANNEL_OPTIONS = (
    (AIRBNB, AIRBNB),
    (BOOKINGCOM, BOOKINGCOM),
    (HOMEAWAY, HOMEAWAY),
    (STAYD, STAYD),
    (ONLY_APARTMENTS, ONLY_APARTMENTS))

CHANNELS = [
    AIRBNB, BOOKINGCOM, HOMEAWAY, STAYD, RENTALS_UNITED, ONLY_APARTMENTS]
SHORT_CHANNEL_NAMES = ('airbnb', 'booking', 'homeaway', 'stayd.com')

THEY_ASSUME_CC_RISK_CHANNELS = [AIRBNB, ONLY_APARTMENTS]
THEY_TAKE_SECURITY_DEPOSIT = [AIRBNB]


def safe_channel(unsafe_channel):
  if unsafe_channel:
    for channel in CHANNELS:
      if channel.lower() == unsafe_channel.lower():
        return channel


def they_assume_cc_risk(channel):
  return safe_channel(channel) in THEY_ASSUME_CC_RISK_CHANNELS


def we_assume_cc_risk(channel):
  return not they_assume_cc_risk(channel)


def cc_photo_required(channel):
  we_take_security_deposit = channel not in THEY_TAKE_SECURITY_DEPOSIT
  return we_assume_cc_risk(channel) or we_take_security_deposit
