AIRBNB = 'Airbnb'
BOOKINGCOM = 'Booking.com'
HOMEAWAY = 'HomeAway'
GUESTY = 'Guesty'  # This happens when you manually make a listing in Guesty.

CHANNELS = (
    (AIRBNB, AIRBNB),
    (BOOKINGCOM, BOOKINGCOM),
    (HOMEAWAY, HOMEAWAY))

SHORT_CHANNEL_NAMES = ('airbnb', 'booking', 'homeaway')

THEY_ASSUME_CC_RISK_CHANNELS = [AIRBNB]
