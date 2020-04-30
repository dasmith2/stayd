"""
Is guesty giving you a weird name for the channel, and you want to put
something in place so our database has something readable?
get_channel_from_source in guesty.api.Guesty has all those.

If you're messing around in here, you might need to update such things as

_explain_why_id_paid_security_deposit_not_ok in
  guest_messages/models/message.py
explain_why_not_check in id_verify/models.py
explain_cc_action_required in reservations.models.py
"""

# When you add anything to this list, make sure it's in the CHANNELS variable
# bellow. You will be nagged by
# guest_messages/template_tags.py#_handle_channel_tags if you forget. Also add
# your new channel to THEY_ASSUME_CC_RISK_CHANNELS or
# THEY_TAKE_SECURITY_DEPOSIT as appropriate.
AIRBNB = 'Airbnb'
BOOKINGCOM = 'Booking.com'
HOMEAWAY = 'HomeAway'
HOWARD = 'Howard'
RENTALS_UNITED = 'RentalsUnited'
ONLY_APARTMENTS = 'OnlyApartments'
MISTER_B_AND_B = 'MrB_and_B'
CANADA_STAYS = 'CanadaStays'
# The rare circumstance where the reservation doesn't go through any OTA or
# website or anything of that nature.
# https://app.guesty.com/reservations/5c51b3350bb9da001ff32f82/guests
DIRECT = 'Direct'


# I'm told we're able to get reservations from these channels, we just haven't
# actually gotten any yet so who knows what Guesty will decide to put in the
# source field.
TRIP_ADVISOR = None
NINE_FLATS = None
DESPEGAR = None
HOPPIFY = None

CHANNEL_OPTIONS = (
    (AIRBNB, AIRBNB),
    (BOOKINGCOM, BOOKINGCOM),
    (HOMEAWAY, HOMEAWAY),
    (HOWARD, HOWARD),
    (ONLY_APARTMENTS, ONLY_APARTMENTS))

# list(filter(None because if you do, like,
# Reservation.objects.filter(~Q(channel__in=THEY_ASSUME_CC_RISK_CHANNELS)) and
# THEY_ASSUME_CC_RISK_CHANNELS contains a None value, you get unexpected
# results. But also a stupid problem that bit me a bunch of times was
# forgetting to add the above channels to the appropriate lists down here, so
# I'm trying to get ahead of it and add them now even though we don't know what
# they're called yet.
CHANNELS = list(filter(None, [
    AIRBNB, BOOKINGCOM, HOMEAWAY, HOWARD, RENTALS_UNITED, ONLY_APARTMENTS,
    MISTER_B_AND_B, DIRECT, CANADA_STAYS, TRIP_ADVISOR, NINE_FLATS, DESPEGAR,
    HOPPIFY]))
SHORT_CHANNEL_NAMES = ('airbnb', 'booking', 'homeaway', 'stayd.com')

THEY_ASSUME_CC_RISK_CHANNELS = list(filter(None, [
    AIRBNB, ONLY_APARTMENTS, TRIP_ADVISOR, MISTER_B_AND_B, CANADA_STAYS]))
WE_ASSUME_CC_RISK_CHANNELS = list(
    set(CHANNELS) - set(THEY_ASSUME_CC_RISK_CHANNELS))
THEY_TAKE_SECURITY_DEPOSIT = list(filter(None, [
    AIRBNB, TRIP_ADVISOR, CANADA_STAYS]))
# Yeah. Some channels integrate quite incompletely with Guesty, so Guesty never
# finds out if we got paid. So we make the extremely dubious assumption that we
# got paid.
PAYMENTS_DONT_SYNC = [ONLY_APARTMENTS, CANADA_STAYS]


def safe_channel(unsafe_channel):
  if unsafe_channel:
    for channel in CHANNELS:
      if channel.lower() == unsafe_channel.lower():
        return channel


def they_assume_cc_risk(channel):
  return safe_channel(channel) in THEY_ASSUME_CC_RISK_CHANNELS


def we_assume_cc_risk(channel):
  return safe_channel(channel) in WE_ASSUME_CC_RISK_CHANNELS


def we_take_security_deposit(channel):
  return channel not in THEY_TAKE_SECURITY_DEPOSIT


def cc_photo_required(channel):
  return we_assume_cc_risk(channel) or we_take_security_deposit(channel)
