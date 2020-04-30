""" Whew. OK if you set a Boolean Guesty custom field to False in the user
interface, you know what the API does? Just stops returning that value. You
know what Guesty does if you just never set that value in the first place? Same
thing. So if you pull down all the custom fields for a reservation, you'll
notice something peculiar. There's no 'value': False anywhere to be seen! Ever!
So let's say you add a new custom field. Now all the existing reservations
simply don't return that value. So there's really no way to tell if a boolean
custom field is set to off or was just never set in the first place, which
means you can't have any kind of a default value besides False. Therefore THE
ONLY WAY TO HAVE A NEW CUSTOM FIELD RETURN TRUE IS TO GO THROUGH THE EFFORT OF
FLIPPING IT ON FOR AAAAALL YOUR EXISTING RESERVATIONS. I've spent years
complaining about how little sense their boolean custom fields make. Nobody
else even understands the issue. """
DEFAULT_GUESTY_FLAG_VALUE = False  # Never ever change this. I'm sorry!


""" To find one of these, first open the developer console and go to the
Network tab. (I know, right?) Now go to
https://app.guesty.com/account/system/custom-fields filter for
me?fields=customFields click on the one whose method is GET, and track down the
response text. In the Firefox console you go to the Response tab on the right
and scroll all the way down to "Response payload". You can select some of it
then ctrl+a to select all of it, copy, paste in a text document. You'll find
your ID in there.

Guesty custom fields. The individual automation field ids are configured in
the guesty_custom_field_id of guest_messages.models.SMSTemplate and SMS.
That's why you don't see them here. """
ID_VERIFIED_FIELD_ID = '5af5fd0dc3c35f0025b2642e'
RISK_SCORE_FIELD_ID = '5b06aa98542e7f002a428c9d'
EMAIL_PROVIDED_FIELD_ID = '5af5fd0dc3c35f0025b2642d'
PHONE_PROVIDED_FIELD_ID = '5af5fd0dc3c35f0025b2642c'
CANARY_IN_THE_COALMINE_FIELD_ID = '5afa2c379ebb42009e34f271'
TRUST_ME_CC_AUTHORIZED = '5b9fd9409ee88c00443d8984'
PAID_IN_FULL_FIELD_ID = '5afed6c3c28d460024347bf8'
CREDIT_CARD_AUTHORIZATION_VALID_FIELD_ID = '5afed6c3c28d460024347bf7'
COMPLETE_ID_VERIFICATION_EMAIL_FIELD_ID = '5afec8950c6ec3001f42e5b3'
GUEST_FEEDBACK_FORM_LINK_FIELD_ID = '5bcdf29c28ae6d003e3cf9f1'
ID_VERIFICATION_LINK_FIELD_ID = '5beef0c5f04633003de066ad'
IS_TEST_RESERVATION_FIELD_ID = '5c1a7d212328110027103c83'
ENTER_1_TO_ACTIVATE_LISTING_IN_KEYS = '5d35e212f377f6001f99fd80'


""" Message stuff """
MESSAGE_WHEN_GUEST_BOOKS = '5afec8950c6ec3001f42e5b6'
REQUEST_TO_COMPLETE_ID_EMAIL = '5afec8950c6ec3001f42e5b5'
REQUEST_TO_COMPLETE_ID_SMS = '5afec8950c6ec3001f42e5b4'
REMINDER_TO_COMPLETE_ID_SMS = '5afec8950c6ec3001f42e5b2'
CHECKIN_INSTRUCTIONS_EMAIL = '5afa2c379ebb42009e34f26f'
SMS_CONFIRMING_GUEST_RECEIVED_INSTRUCTIONS = '5afa2c379ebb42009e34f26e'
DAY_OF_CHECKIN_SMS = '5afa2c379ebb42009e34f26d'
HOWS_EVERYTHING_SMS = '5afa2c379ebb42009e34f26c'
CHECKOUT_INSTRUCTIONS_EMAIL = '5afa2c379ebb42009e34f26b'
MORNING_OF_CHECKOUT_SMS = '5afa2c379ebb42009e34f26a'
FEEDBACK_REQUEST_SMS = '5b299253f2177301cca1269a'
NPS_RATE_US_EMAIL = '5d6ed1c2955c1c00240cace7'  # a.k.a. NPS Net Promotor Score
GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS = (
    (MESSAGE_WHEN_GUEST_BOOKS, (  # Not actually used by keys.
        'Message when guest books (on Channel- at time of booking)')),
    (REQUEST_TO_COMPLETE_ID_EMAIL, (  # Not actually used by keys.
        'Request for ID verification (Email- at time of booking)')),
    (REQUEST_TO_COMPLETE_ID_SMS, (
        'Request to complete ID verification (SMS- 3 hrs after booking)')),
    (REMINDER_TO_COMPLETE_ID_SMS, (
        'Reminder to complete ID verification (SMS- 26 hrs after booking)')),
    (CHECKIN_INSTRUCTIONS_EMAIL, (
        'Check-in instructions email (2 days before check-in)')),
    (SMS_CONFIRMING_GUEST_RECEIVED_INSTRUCTIONS, (
        'SMS confirming guest received check-in instructions '
        '(2 days before check-in)')),
    (DAY_OF_CHECKIN_SMS, 'Day of check-in SMS'),
    (HOWS_EVERYTHING_SMS, (
        '"How\'s everything at the apartment?" SMS '
        '(morning after arrival)')),
    (CHECKOUT_INSTRUCTIONS_EMAIL, (
        'Checkout instructions email (day before checkout)')),
    (MORNING_OF_CHECKOUT_SMS, 'Morning of checkout SMS'),
    (FEEDBACK_REQUEST_SMS, (
        'Guest feedback request (SMS 3 days after checkout)')),
    (NPS_RATE_US_EMAIL, (
        'Request guest feedback so we can calc Net Promotor Score')))
