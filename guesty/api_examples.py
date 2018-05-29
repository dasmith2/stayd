# flake8: noqa
from django.conf import settings

WEBHOOKS = [{
    '__v': 0,
    '_id': '5aec7e9e462dc3004b58339d',
    'accountId': '5ad78474940b9f002c818682',
    'events': ['task.updated'],
    'url': 'https://stayd-stage.herokuapp.com/guesty_webhook/task.updated'}]


RESERVATION_FOR_LIST = {
    '_id': '5ade4d3314fe0e004dcde909',
    'accountId': '5ad78474940b9f002c818682',
    'checkIn': '2018-01-03T20:00:00.000Z',
    'checkOut': '2018-01-12T16:00:00.000Z',
    'confirmationCode': 'HM123456',
    'guest': {'_id': '5ade4ca7a989550061844c3b', 'fullName': 'Sofia Fay'},
    'guestId': '5ade4ca7a989550061844c3b',
    'integration': {
        '_id': '5adde0b04a487600302af41c',
        'limitations': {'availableStatuses': []},
        'platform': 'airbnb'},
    'listing': {
        '_id': '5ade48915ac9b90011ab64cc',
        'title': 'SPACIOUS 3BR/2BA **2 STOPS FROM NYC** SLEEPS 10!!!'},
    'listingId': '5ade48915ac9b90011ab64cc'}


RESERVATION = {
    '_id': '5ade4d3314fe0e004dcde909',
    'accountId': '5ad78474940b9f002c818682',
    'cancellationPolicy': 'Strict (grace period)',
    'checkIn': '2018-01-03T20:00:00.000Z',
    'checkInDateLocalized': '2018-01-03',
    'checkOut': '2018-01-12T16:00:00.000Z',
    'checkOutDateLocalized': '2018-01-12',
    'closedAt': '2018-04-24T13:42:29.441Z',
    'plannedArrival': '17:00',
    'confirmationCode': 'HM123456',
    'confirmedAt': '2018-04-23T21:16:35.272Z',
    'createdAt': '2018-04-23T21:16:35.273Z',
    'customFields': [{
        'fieldId': settings.EMAIL_PROVIDED_FIELD_ID,
        'value': 'sophia@gmail.com'}],
    'guestId': '5ade4ca7a989550061844c3b',
    'guestsCount': 4,
    'importedAt': '2018-04-23T21:16:35.272Z',
    'integration': {
        '_id': '5adde0b04a487600302af41c',
        'airbnb': {
            'guestId': 92547277, 'id': 578107353, 'listingId': 21679272},
        'limitations': {'availableStatuses': []},
        'platform': 'airbnb'},
    'isReturningGuest': True,
    'listing': {
        '_id': '5ade48915ac9b90011ab64cc',
        'address': {
            'full': (
                '144 Steuben Street Apt #402, Jersey City, '
                'NJ 07302, United States')},
        'nickname': 'SPACIOUS 3BR/2BA **2 STOPS FROM NYC** SLEEPS 10!!!',
        'picture': {'thumbnail': '...thumbnail_410277904.jpg'},
        'title': 'SPACIOUS 3BR/2BA **2 STOPS FROM NYC** SLEEPS 10!!!'},
    'listingId': '5ade48915ac9b90011ab64cc',
    'log': [{
        '_id': '5ade4d3314fe0e004dcde911',
        'at': '2018-04-23T21:16:35.337Z',
        'changes': [],
        'event': 'Booking was imported successfully'}, {
        '_id': '5ae032af1ca98b0029820b35',
        'at': '2018-04-25T07:47:59.587Z',
        'by': 'jordan via Michael Jaindl',
        'changes': [{
            '_id': '5ae032af1ca98b0029820b50',
            'diff': [{
                '_id': '5ae032af1ca98b0029820b52',
                'removed': True,
                'value': 'false'}, {
                '_id': '5ae032af1ca98b0029820b51',
                'added': True,
                'value': 'true'}],
            'field': 'money isFullyPaid'}, {
            '_id': '5ae032af1ca98b0029820b4d',
            'diff': [{
                '_id': '5ae032af1ca98b0029820b4f',
                'removed': True,
                'value': '1321.14'}, {
                '_id': '5ae032af1ca98b0029820b4e',
                'added': True,
                'value': '0'}],
            'field': 'money balanceDue'}, {
            '_id': '5ae032af1ca98b0029820b4a',
            'diff': [{
                '_id': '5ae032af1ca98b0029820b4c',
                'removed': True,
                'value': '0'}, {
                '_id': '5ae032af1ca98b0029820b4b',
                'added': True,
                'value': '1321.14'}],
            'field': 'money totalPaid'}],
        'event': 'Reservation was updated'}],
    'money': {
        'autoPaymentsPolicy': [],
        'balanceDue': 0,
        'commission': 1321.14,
        'commissionFormula': 'net_income',
        'commissionIncTax': 1321.14,
        'commissionTax': 0,
        'commissionTaxPercentage': 0,
        'currency': 'BZD',
        'fareAccommodation': 1262,
        'fareCleaning': 100,
        'hostPayout': 1321.14,
        'hostPayoutUsd': 1321.14,
        'hostServiceFee': 40.86,
        'invalidCreditCard': None,
        'invoiceItems': [{
            '_id': '5ade4d3314fe0e004dcde90a',
            'amount': 1262,
            'currency': 'BZD',
            'isLocked': True,
            'title': 'Accommodation fare'}, {
            '_id': '5ade4d3314fe0e004dcde90b',
            'amount': 100,
            'currency': 'BZD',
            'isLocked': True,
            'title': 'Cleaning fee'}, {
            '_id': '5ade4d3314fe0e004dcde90c',
            'amount': -40.86,
            'currency': 'BZD',
            'isLocked': True,
            'title': 'Host channel fee'}],
        'isFullyPaid': True,
        'isTouchedPayments': True,
        'netIncome': 1321.14,
        'netIncomeFormula': 'host_payout',
        'ownerRevenue': 0,
        'payments': [{
            'status': 'AUTHORIZATION_HOLD_SUCCEEDED',
            'amount': 300,
            'currency': 'BOV',}, {
            '_id': '5ae032af1ca98b0029820b34',
            'amount': 1321.14,
            'attempts': [],
            'authorizationHoldCaptures': [],
            'createdAt': '2018-04-25T07:47:59.544Z',
            'currency': 'BZD',
            'guestId': '5ade4ca7a989550061844c3b',
            'isAuthorizationHold': False,
            'paidAt': '2018-04-25T07:47:59.543Z',
            'paymentMethodId': '589894a91d756b9c47ce1e87',
            'receiptId': 15891687,
            'receiptTargets': [],
            'refunds': [],
            'shouldBePaidAt': '2018-04-25T07:47:59.543Z',
            'status': 'SUCCEEDED'}],
        'paymentsDue': 0,
        'subTotalPrice': 1362,
        'totalPaid': 1321.14,
        'totalRefunded': 0},
    'nightsCount': 9,
    'preCancelationMoney': {
        'autoPaymentsPolicy': [],
        'invoiceItems': [],
        'payments': []},
    'review': {'shouldReview': True},
    'source': 'BookingCom', # I also saw Airbnb
    'status': 'confirmed'}


LISTING = {
    'SaaS': {'autoRenew': True},
    '__v': 24,
    '_id': '5ade48915ac9b90011ab64cc',
    'accommodates': 10,
    'accountId': '5ad78474940b9f002c818682',
    'active': True,
    'address': {
        'apt': 'Apt #402',
        'city': 'Jersey City',
        'country': 'United States',
        'full': (
            '144 Steuben Street Apt #402, Jersey City, NJ 07302, '
            'United States'),
        'lat': 40.719452,
        'lng': -74.039574,
        'searchable': (
            '144 Steuben Street , Jersey City, NJ 07302, United States'),
        'state': 'NJ',
        'street': '144 Steuben Street',
        'zipcode': '07302'},
    'amenities': ['TV', 'Wide entryway'],
    'amenitiesNotIncluded': ['Internet', 'Wheelchair accessible'],
    'bathrooms': 2,
    'bedType': 'Real Bed',
    'bedrooms': 3,
    'beds': 5,
    'calendarRules': {
        'defaultAvailability': 'AVAILABLE',
        'rentalPeriods': [],
        'seasonalMinNights': [{
            '_id': '5ae89279f49d2600399299c3',
            'from': '2018-05-01',
            'minNights': 1,
            'to': '2018-05-03'}, {
            '_id': '5ae89279f49d2600399299c4',
            'from': '2018-05-04',
            'minNights': 2,
            'to': '2018-05-05'}, {
            '_id': '5ae89279f49d2600399299cb',
            'from': '2018-10-19',
            'minNights': 3,
            'to': '2019-05-01'}],
        'weekendMinNights': 2},
    'createdAt': '2018-04-23T20:56:49.722Z',
    'customFields': [],
    'defaultCheckInTime': '15:00',
    'defaultCheckOutTime': '11:00',
    'importedAt': '2018-04-23T20:56:49.727Z',
    'importingPlatform': 'airbnb',
    'instantBookable': {
        'enabled': True,
        'leadTime': 9,
        'visibility': 'experienced_guest_with_government_id'},
    'integrations': [
        {'platform': 'airbnb',
         '_id': '5af593fffe522800208d36cf',
         'externalUrl': 'https://www.airbnb.com/rooms/21304904',
         'bookingCom': {'errors': [], 'acceptedCreditCards': []},
         'airbnb': {'starRating': 4.5,
          'reviewsCount': 20,
          'id': 21679272,
          'isCalendarSynced': True}},
        {'platform': 'rentalsUnited',
         '_id': '5afae33b3766e000248f3844',
         'bookingCom': {'errors': [], 'acceptedCreditCards': []},
         'rentalsUnited': {
             'id': 1847201, 'currency': 'USD', 'locationId': '16864'}}],
    'isListed': True,
    'lastActivityAt': '2018-05-01T16:18:06.911Z',
    'lastSyncedAt': '2018-05-01T16:15:04.148Z',
    'lastUpdatedAt': '2018-05-01T16:15:04.208Z',
    'listingRooms': [{
        '_id': '5ae8928899dab0002f7a6b51',
        'beds': [{
            '_id': '5ae8928899dab0002f7a6b52',
            'quantity': 1,
            'type': 'KING_BED'}],
        'id': 12823258,
        'roomNumber': 1}, {
        '_id': '5ae8928899dab0002f7a6b53',
        'beds': [{
            '_id': '5ae8928899dab0002f7a6b54',
            'quantity': 1,
            'type': 'QUEEN_BED'}],
        'id': 12823259,
        'roomNumber': 3}, {
        '_id': '5ae8928899dab0002f7a6b55',
        'beds': [{
            '_id': '5ae8928899dab0002f7a6b56',
            'quantity': 1,
            'type': 'QUEEN_BED'}],
        'id': 12823260,
        'roomNumber': 2}, {
        '_id': '5ae8928899dab0002f7a6b57',
        'beds': [{
            '_id': '5ae8928899dab0002f7a6b58',
            'quantity': 2,
            'type': 'SOFA_BED'}],
        'id': 12823261,
        'roomNumber': 0}],
    'nickname': 'SPACIOUS 3BR/2BA **2 STOPS FROM NYC** SLEEPS 10!!!',
    'occupancyStats': [],
    'offeredServices': [],
    'owners': [],
    'pendingTasks': [],
    'picture': {
        'caption': '',
        'large': '...large_410277904.jpg',
        'regular': '...regular_410277904.jpg',
        'thumbnail': '...thumbnail_410277904.jpg'},
    'pictures': [{
        '_id': '5ae8928899dab0002f7a6b46',
        'caption': '',
        'id': 410277904,
        'large': 'large_410277904.jpg',
        'original': '...original_410277904.jpg',
        'regular': '...regular_410277904.jpg',
        'sort': 1,
        'thumbnail': '...thumbnail_410277904.jpg'}, {
        '_id': '5ae8928899dab0002f7a6b50',
        'caption': '',
        'id': 410278020,
        'large': '...large_410278020.jpg',
        'original': '...original_410278020.jpg',
        'regular': '...regular_410278020.jpg',
        'sort': 11,
        'thumbnail': '...thumbnail_410278020.jpg'}],
    'pms': {
        'active': True,
        'autoPayments': {'policy': []},
        'automation': {
            'answeringMachine': {
                'confirmedAfterCheckOut': {'delayInMinutes': 45},
                'confirmedBeforeCheckIn': {'delayInMinutes': 45},
                'confirmedDayOfCheckIn': {'delayInMinutes': 45},
                'confirmedDayOfCheckOut': {'delayInMinutes': 45},
                'confirmedDuringStay': {'delayInMinutes': 45},
                'unconfirmedFirstMessage': {'delayInMinutes': 55},
                'unconfirmedSubsequentMessage': {'delayInMinutes': 45}},
            'autoPricing': {'rules': []},
            'autoReviews': {'templates': []},
            'calendarSmartRules': {'blockListings': []},
            'hooks': {'ignoredHooks': []}},
        'tasks': {'defaultTasks': []}},
    'preBooking': [],
    'prices': {
        'basePrice': 199,
        'basePriceUSD': 199,
        'cleaningFee': 100,
        'currency': 'BZD',
        'extraPersonFee': 25,
        'guestsIncludedInRegularFee': 6,
        'monthlyPriceFactor': 1,
        'securityDepositFee': 300,
        'weeklyPriceFactor': 1},
    'privateDescription': {
        'wifi': {'network': 'Stayd', 'password': 'travelwell'}},
    'propertyType': 'Apartment',
    'publicDescription': {
        'access': "It's your entire private apartment.",
        'guestControls': {
            'allowsChildren': True,
            'allowsEvents': False,
            'allowsInfants': True,
            'allowsPets': False,
            'allowsSmoking': False},
        'houseRules': 'No smoking',
        'interactionWithGuests': 'We are standing by.',
        'neighborhood': 'Features: Strollers',
        'notes': 'Jersey City is a lively metropolitan area.',
        'space': 'Comfortable, safe, clean.',
        'summary': 'Create a memorable vacation or business trip.',
        'transit': 'The Grove Street PATH Station is a 6-minute walk.'},
    'receptionistsService': {
        'receptionDesk': {'atPhones': [], 'ittt': []},
        'screening': {'checklist': []}},
    'roomType': 'Entire home/apt',
    'sales': {'salesService': {'atPhones': []}},
    'tags': [],
    'taxes': [],
    'terms': {
        'cancellation': 'strict_14_with_grace_period',
        'maxNights': 1125,
        'minNights': 1},
    'timezone': 'America/New_York',
    'title': '8 eerie #9 or whatever',
    'useAccountTaxes': False}


LIST_LISTINGS = {
    'count': 1,
    'fields': '',
    'limit': 25,
    'skip': 0,
    'title': 'Listings Report',
    'results': [LISTING]}


GUEST = {
    '__v': 3,
    '_id': '5ade4ca7a989550061844c3b',
    'accountId': '5ad78474940b9f002c818682',
    'airbnb': {
        'firstName': 'Sofia',
        'fullName': 'Sofia Fay',
        'id': 92547277,
        'lastName': 'Fay',
        'url': 'https://www.airbnb.com/users/show/92547277'},
    'communicationMethods': ['airbnb', 'sms'],
    'confirmed': True,
    'email': 'jiaxin-ku0lh5ltfwqd0be5@guest.airbnb.com',
    'emails': ['jiaxin-ku0lh5ltfwqd0be5@guest.airbnb.com'],
    'firstName': 'Sofia',
    'fullName': 'Sofia Fay',
    'hasVerifiedId': True,
    'hometown': 'Tortola, British Virgin Islands', # Optional
    'languages': '',
    'lastName': 'Fay',
    'paymentMethodIds': [],
    'phone': '16178177271',
    'phones': ['16178177271'],
    'picture': {
        '_id': '5ade4ca7a989550061844c3c',
        'large': '...large_9a655c5b-176c-48a6-bbb1-28727f0f6de2.jpg',
        'regular': '...regular_9a655c5b-176c-48a6-bbb1-28727f0f6de2.jpg',
        'thumbnail': '...thumbnail_9a655c5b-176c-48a6-bbb1-28727f0f6de2.jpg'},
    'pictures': [{
        '_id': '5ade4ca7a989550061844c3c',
        'large': '...large_9a655c5b-176c-48a6-bbb1-28727f0f6de2.jpg',
        'regular': '...regular_9a655c5b-176c-48a6-bbb1-28727f0f6de2.jpg',
        'thumbnail': '...thumbnail_9a655c5b-176c-48a6-bbb1-28727f0f6de2.jpg'}],
    'verifications': [
        'Email address',
        'Phone number',
        'Reviewed',
        'Government ID',
        'Selfie']}
