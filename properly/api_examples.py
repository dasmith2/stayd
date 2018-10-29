# flake8: noqa

CANCEL_JOB = {
    "clientRequestId": "7a53c0e70f543b65ecc76fa5",
    "apiRequestId": "5a53c0e70f324b65ecc76ea5",
    "createdAt":"2018-01-08T19:05:11.968Z",
    "targetAccountId":"6a53c0wdsfde343242334kj9",
    "jobRequest.canceled": [{
            "jobRequestId": "d8h38hf8h8fh38h83ff3rw"
        }
    ]
}


SET_SOURCE_PROPERTY_ID_RESPONSE = {'apiRequestId': '5bcf39376fdaa017f1ecea9d',
 'createdAt': '2018-10-23T15:07:35.917Z',
 'targetAccountId': 'dx5qm9s0eb',
 'clientRequestId': 'J384T7L',
 'property.update': [{'propertyId': '2IfUXrNlyD'}]}


# We send this...
REQUEST_CREATE_JOB = {'targetAccountId': 'dx5qm9s0eb',
 'clientRequestId': 'I4AYVXP',
 'jobRequest.create': [{'sourceBookingId': 'HMFANRF8NM',
   'receiveUpdates': True,
   'time': {'type': 'fixed',
    'startTime': '2018-10-28T15:15:00Z',
    'durationInHours': 3},
   'property': {'sourcePropertyId': '2IfUXrNlyD'},
   'checklists': [{'checklistId': '1K6BGKUQlK'}],
   'serviceProviders': [{'email': 'dave@stayd.com'}]}]}


# And get this back.
CREATE_JOB = {'apiRequestId': '5bce266701ff157aa6e21655',
 'createdAt': '2018-10-22T19:35:03.966Z',
 'targetAccountId': 'dx5qm9s0eb',
 'clientRequestId': 'I4AYVXP',
 'jobRequest.create': [{'jobRequestId': '5bce266701ff159cd2e21656'}]}


SETUP_WEBHOOK = {
  '_id': '5ba344fea27b3fe9bcfafdc8',
  'targetAccountId': '5ba34160038ee834c1a1b651',
  'apiKeys': ['8N9OQ93KPX9kFpaH7g3224ppHHkSeeIs85LkJX4r'],
  'name': 'STAYD_Sandbox',
  'webhooks': [{'url': 'https://stage.stayd.com/properly/webhook',
    'eventName': '*',
    'id': '5ba9193eaacb7200010e9dbd'}],
  'updatedAt': '2018-09-24T17:05:02.185Z',
  'lastUpdate': {'clientRequestId': 'IBXXV38',
   'apiRequestId': '5ba9193eaacb7200010e9dbc'}}


ERROR_RESPONSE = {'apiRequestId': '5bce3c8dd417dc07aaa92446',
 'createdAt': '2018-10-22T21:09:33.624Z',
 'targetAccountId': 'dx5qm9s0eb',
 'clientRequestId': 'R93ML8E',
 'jobRequest.create': [{'errors': [{'type': 'object.unknownProperties',
     'expected': ['sourcePropertyId',
      'information',
      'access',
      'garbage',
      'parking',
      'wifiName',
      'wifiPassword',
      'wifiDescription',
      'otherAttributes'],
     'actual': ['propertyId'],
     'field': 'property',
     'message': "The 'property' object field  has the following allowed properties sourcePropertyId,information,access,garbage,parking,wifiName,wifiPassword,wifiDescription,otherAttributes , but received the following unknown properties: propertyId "},
    {'type': 'required',
     'field': 'property.sourcePropertyId',
     'message': "The 'property.sourcePropertyId' field is required!"}]}]}


ERROR_WEBHOOK = {'clientRequestId': 'I4AYVXP',
 'apiRequestId': '5bce266701ff157aa6e21655',
 'targetAccountId': 'dx5qm9s0eb',
 'createdAt': '2018-10-22T19:35:03.966Z',
 'notifiedAt': '2018-10-22T19:39:35.924Z',
 'eventName': 'jobRequest.create',
 'input': {'sourceBookingId': 'HMFANRF8NM',
  'receiveUpdates': True,
  'time': {'type': 'fixed',
   'startTime': '2018-10-28T15:15:00Z',
   'durationInHours': 3},
  'property': {'sourcePropertyId': '2IfUXrNlyD'},
  'checklists': [{'checklistId': '1K6BGKUQlK'}],
  'serviceProviders': [{'email': 'dave@stayd.com'}],
  'jobRequestId': '5bce266701ff159cd2e21656'},
 'results': [{'error': 'Could not find a property for sourcePropertyId: 2IfUXrNlyD'}]}


SET_SOURCE_ID_RESPONSE = {'clientRequestId': '2H3RKOP',
 'apiRequestId': '5bcf41816fdaa0f44beceaa7',
 'targetAccountId': 'dx5qm9s0eb',
 'createdAt': '2018-10-23T15:42:57.516Z',
 'notifiedAt': '2018-10-23T15:42:59.914Z',
 'eventName': 'property.update',
 'input': {'propertyId': '2IfUXrNlyD', 'changes': {'sourceId': '2IfUXrNlyD'}},
 'results': [{'propertyId': '2IfUXrNlyD',
   'name': '185 Newark Ave #4 Jersey City, NJ',
   'details': {'information': '-Keys must be placed in the main and back up lockboxes when the cleaning is finished\n-Leave two extra sets of keys on the coffee table in the living room\n\nSMS or call 646-713-0582 with any questions.\n',
    'access': 'Option 1: Use main lockbox on front door of building labeled "lockbox #4". The code is 1289.\nOption 2: Use backup lockbox on front door of building labeled "backup lockbox". The code is 9821.\nOption 3: Used second backup lockbox. The code is 7531.',
    'garbage': '-Garbage and recycling should be sorted and placed in tied trash bags. \n-The trash and recycling cans are located on the 4th floor.',
    'wifiName': 'Stayd',
    'wifiPassword': 'travelwell'},
   'sourceId': '2IfUXrNlyD',
   'location': {'longitude': -74.0456623, 'latitude': 40.7211434},
   'createdAt': '2018-07-01T14:33:11.290Z',
   'updatedAt': '2018-10-23T15:42:59.045Z',
   'targetAccountId': 'dx5qm9s0eb',
   'countryCode': 'US',
   'timeZone': 'America/New_York',
   'type': 'apartment',
   'address': {'apt': '',
    'city': 'Jersey City',
    'country': 'United States',
    'state': 'NJ',
    'street': '185 Newark Avenue Apartment #4',
    'zip': '07302',
    'AddressArray': ['185 Newark Avenue Apartment #4',
     'Jersey City NJ 07302',
     'United States']},
   'bedrooms': 3,
   'beds': 4,
   'bathrooms': 1,
   'tags': []}]}
