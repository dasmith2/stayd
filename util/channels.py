AIRBNB = 'Airbnb'
BOOKINGCOM = 'Booking.com'
HOMEAWAY = 'HomeAway'
STAYD = 'reservations.stayd.com'
RENTALS_UNITED = 'RentalsUnited'

CHANNEL_OPTIONS = (
    (AIRBNB, AIRBNB),
    (BOOKINGCOM, BOOKINGCOM),
    (HOMEAWAY, HOMEAWAY),
    (STAYD, STAYD))

CHANNELS = [AIRBNB, BOOKINGCOM, HOMEAWAY, STAYD, RENTALS_UNITED]
SHORT_CHANNEL_NAMES = ('airbnb', 'booking', 'homeaway', 'stayd.com')

THEY_ASSUME_CC_RISK_CHANNELS = [AIRBNB]


def safe_channel(unsafe_channel):
  if unsafe_channel:
    for channel in CHANNELS:
      if channel.lower() == unsafe_channel.lower():
        return channel


def they_assume_cc_risk(channel):
  return safe_channel(channel) in THEY_ASSUME_CC_RISK_CHANNELS


def we_assume_cc_risk(channel):
  return not they_assume_cc_risk(channel)
