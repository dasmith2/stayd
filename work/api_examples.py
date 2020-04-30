# flake8: noqa
import json

CLEANING_JOBS_KICK_OFF = {'apiRequestId': '5cb4a1cb2d88bfce97c8f2dd',
 'createdAt': '2019-04-15T15:22:51.512Z',
 'targetAccountId': 'dx5qm9s0eb',
 'clientRequestId': 'PQGNIGI',
 'listing.cleaningJobs': [{'message': 'Listing Request Complete'}]}


CLEANING_JOBS_RESULTS = {
  "clientRequestId": "OYTN4CX",
  "apiRequestId": "5cb4a2922d88bfc9d7c8f2df",
  "targetAccountId": "dx5qm9s0eb",
  "notifiedAt": "2019-04-15T15:26:12.882Z",
  "eventName": "listing.cleaningJobs",
  "input": {
    "dateFrom": "2019-04-18 00:00:00",
    "dateTo": "2019-04-21 00:00:00"
  },
  "results": [{
      "_id": "5cb375685322e58586eddbe7",
      "scheduledStartTime": "2019-04-14T18:11:11.975Z",
      "scheduledEndTime": "2019-04-14T20:39:48.000Z",
      "propertyId": "xrhoa71I8t",
      "hostId": "dx5qm9s0eb",
      "actualEndTime": "2019-04-14T18:43:00.660Z",
      "actualStartTime": "2019-04-14T18:28:31.413Z",
      "status": 7,
      "jobId": "5cb375685322e58586eddbe7",
      "cleanerId": "dSZnGjhNRE",
      "createdTime": "2019-04-14T18:01:12.636Z",
      "propertyTitle": "315 2nd St #4 Jersey City, NJ",
      "sourceId": "xrhoa71I8t",
      "address": {
        "street": "315 2nd St",
        "apt": "#4",
        "city": "Jersey City",
        "country": "United States",
        "manualEntry": False,
        "zoomLevel": 0,
        "zip": "07302",
        "AddressArray": [
          "315 2nd St",
          "Jersey City NJ 07302",
          "Jersey City NJ 07302"
        ],
        "state": "NJ"
      },
      "location": [
        -74.0472604,
        40.7226715
      ],
      "cleanerEmail": "naijshua@gmail.com"
    },
{
      "_id": "5cb404038303388223fc6135",
      "scheduledStartTime": "2019-04-16T15:00:00.000Z",
      "scheduledEndTime": "2019-04-16T16:00:00.000Z",
      "propertyId": "FdRRuD9n3z",
      "hostId": "dx5qm9s0eb",
      "actualEndTime": None,
      "actualStartTime": None,
      "status": 1,
      "jobId": "5cb404038303388223fc6135",
      "createdTime": "2019-04-15T04:09:40.503Z",
      "propertyTitle": "243 Montgomery St #4 Jersey City, NJ",
      "sourceId": "FdRRuD9n3z",
      "address": {
        "apt": "",
        "city": "Jersey City",
        "country": "United States",
        "state": "NJ",
        "street": "243 Montgomery Street Apt #4",
        "zip": "07302",
        "AddressArray": [
          "243 Montgomery Street Apt #4",
          "Jersey City NJ 07302",
          "United States"
        ]
      },
      "location": [
        -74.04562899999999,
        40.71782109999999
      ]
    }]}

BOOKING_CREATE = {
  "clientRequestId": "7a53c0e70f543b65ecc76fa5",
  "apiRequestId": "5a53c0e70f324b65ecc76ea5",
  "createdAt":"2018-01-08T19:05:11.968Z",
  "targetAccountId":"6a53c0wdsfde343242334kj9",
  "booking.create": [{
      "bookingId": "d8h38hf8h8fh38h83ff3rw"}]
}


JOB_STARTED = {
  'clientRequestId': '7a53c0e70f543b65ecc76fa5',
  'apiRequestId': '5a53c0e70f324b65ecc76ea5',
  'targetAccountId':'6a53c0wdsfde343242334kj9',
  'createdAt':'2018-01-08T19:05:11.968Z',
  'notifiedAt':'2018-01-08T19:06:00.328Z',
  'eventName': 'jobRequest.started',
  'results': [{
      'jobRequestId': 'd8h38hf8h8fh38h83ff3rw'
    }
  ]
}


JOB_COMPLETE = {
  'clientRequestId': '7a53c0e70f543b65ecc76fa5',
  'apiRequestId': '5a53c0e70f324b65ecc76ea5',
  'targetAccountId':'6a53c0wdsfde343242334kj9',
  'createdAt':'2018-01-08T19:05:11.968Z',
  'notifiedAt':'2018-01-08T19:06:00.328Z',
  'eventName': 'jobRequest.completed',
  'results': [{
   'jobRequestId': '5cffe19414b48ac5b66f1fce',
   'problems': [{
     'problemId': '5fwbpkF6DWdC1jeZ',
     'pictures': ['https://domain.com/pic1.jpg'],
     'note': 'comment from service provider',
     'reportedAt': '2018-03-22T08:08:10.119Z',
    },
   ],
   'checklists': [{
     'checklistId': 'iuashiu29y298u29hijhs98',
     'taskGroupsCount': 1,
     'tasksCount': 8,
     'verificationRequiredCount': 2,

     'taskGroupsDoneCount': 1,
     'tasksDoneCount': 8,
     'verificationDoneCount': 1,
     'taskGroups': [{
       'taskGroupId': 'djahsiua98y872gi2722',
       'verificationPictures': ['https://domain.com/pic2.jpg', 'https://domain.com/pic3.jpg'],
       'tasks': [{
         'taskId': 'hashasygsad7287wsas',
         'doneAt': '2018-03-22T08:07:10.119Z',
         'done':True
        },
       ],
      },
     ],
    },
   ],
   'serviceProvider': {'name': 'Anita Anita', 'email': 'ab_anita@yahoo.com'}
  },
 ]
}

JOB_COMPLETE_TASKS_INCOMPLETE = {
  'clientRequestId': '7a53c0e70f543b65ecc76fa5',
  'apiRequestId': '5a53c0e70f324b65ecc76ea5',
  'targetAccountId':'6a53c0wdsfde343242334kj9',
  'createdAt':'2018-01-08T19:05:11.968Z',
  'notifiedAt':'2018-01-08T19:06:00.328Z',
  'eventName': 'jobRequest.completed',
  'results': [{
   'jobRequestId': 'd8h38hf8h8fh38h83ff3rw',
   'problems': [{
     'problemId': '5fwbpkF6DWdC1jeZ',
     'pictures': ['https://domain.com/pic1.jpg'],
     'note': 'comment from service provider',
     'reportedAt': '2018-03-22T08:08:10.119Z',
    },
   ],
   'checklists': [{
     'checklistId': 'iuashiu29y298u29hijhs98',
     'taskGroupsCount': 1,
     'tasksCount': 8,
     'verificationRequiredCount': 2,

     'taskGroupsDoneCount': 1,
     'tasksDoneCount': 8,
     'verificationDoneCount': 1,
     'taskGroups': [{
       'taskGroupId': 'djahsiua98y872gi2722',
       'verificationPictures': ['https://domain.com/pic2.jpg', 'https://domain.com/pic3.jpg'],
       'tasks': [{
         'taskId': 'hashasygsad7287wsas',
         'doneAt': '2018-03-22T08:07:10.119Z',
         'done':True
        },{
         'taskId': 'had7287wsas',
         'doneAt': '2018-03-22T08:07:10.119Z',
         'done':False
        }
       ],
      },
     ],
    },
   ],
  },
 ]
}


CANCELED_BY_CLEANER = {
  'clientRequestId': '7a53c0e70f543b65ecc76fa5',
  'apiRequestId': '5a53c0e70f324b65ecc76ea5',
  'targetAccountId':'6a53c0wdsfde343242334kj9',
  'createdAt':'2018-01-08T19:05:11.968Z',
  'notifiedAt':'2018-01-08T19:06:00.328Z',
  'eventName': 'jobRequest.canceledByServiceProvider',
  'results': [{
      'jobRequestId': 'd8h38hf8h8fh38h83ff3rw'
    }
  ]
}

DECLINED_BY_WORKER = {
  "clientRequestId": "5cffd0515a947b6db4d1b8b3",
  "apiRequestId": "5cffd016c75ec5d1955aa3e4",
  "targetAccountId": "dx5qm9s0eb",
  "createdAt": "2019-06-11T16:01:21.071Z",
  "notifiedAt": "2019-06-11T16:01:21.472Z",
  "eventName": "jobRequest.declinedByServiceProvider",
  "results": [
    {
      "jobRequestId": "5cffd016c75ec5a2ae5aa3e5",
      "serviceProvider": "cosmapollo@gmail.com",
      "message": ""
    }
  ]
}

CANCELED = {
  "clientRequestId": "5c04b17f8293d700b48ab9df",
  "targetAccountId": "dx5qm9s0eb",
  "createdAt": "2018-12-03T04:30:55.522Z",
  "notifiedAt": "2018-12-03T04:30:56.224Z",
  "eventName": "jobRequest.canceled",
  "input": {},
  "results": [
    {
      "jobRequestId": "5c01b3135ec893ac8076dda8"
    }
  ]
}


ACCEPTED_JOB_WEBHOOK = {
  "clientRequestId": "5cffe8af5a947b06c4d1b8b7",
  "apiRequestId": "5cffe19414b48a338d6f1fcd",
  "targetAccountId": "dx5qm9s0eb",
  "createdAt": "2019-06-11T17:45:19.166Z",
  "notifiedAt": "2019-06-11T17:45:20.475Z",
  "eventName": "jobRequest.accepted",
  "results": [
    {
      "jobRequestId": "5cffe19414b48ac5b66f1fce",
      "serviceProvider": "nikolagirl@yahoo.com",
      "message": ""
    }
  ]
}


CANCEL_JOB = {
  'clientRequestId': '7a53c0e70f543b65ecc76fa5',
  'apiRequestId': '5a53c0e70f324b65ecc76ea5',
  'createdAt':'2018-01-08T19:05:11.968Z',
  'targetAccountId':'6a53c0wdsfde343242334kj9',
  'jobRequest.canceled': [{
      'jobRequestId': 'd8h38hf8h8fh38h83ff3rw'
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

SOURCE_ID_DIDNT_TAKE = {'clientRequestId': '3NI90Y8',
 'apiRequestId': '5bfc75e56348d8838e7a260c',
 'targetAccountId': 'dx5qm9s0eb',
 'createdAt': '2018-11-26T22:38:29.347Z',
 'notifiedAt': '2018-11-26T22:43:01.370Z',
 'eventName': 'booking.create',
 'input': {'sourcePropertyId': 'NwlTE3dexN',
  'sourceBookingId': 'HMY9N8SZ9P',
  'startDate': '2019-03-11T20:00:00Z',
  'endDate': '2019-03-19T15:00:00Z',
  'title': 'API reservation for Les Beer',
  'numberOfGuests': 1,
  'guestDetails': [{'sourceId': '172099996',
    'firstName': 'Les',
    'lastName': 'Beer'}],
  'bookingId': '5bfc75e56348d840a37a260d'},
 'results': [{'error': 'Could not find a property for sourcePropertyId: NwlTE3dexN'}]}

CHECKLIST_CREATE = {'apiRequestId': '5c104002e5fcd61e758f047f',
 'createdAt': '2018-12-11T22:53:54.965Z',
 'targetAccountId': 'dx5qm9s0eb',
 'clientRequestId': '4HJ6ZYK',
 'checklist.create': [{'checklistId': '5c104002e5fcd6b2df8f0480'}]}

CHECKLIST_CREATE_HOOK = {'clientRequestId': 'HPKNPQY',
 'apiRequestId': '5bfd9feeb9b0812f3857c581',
 'targetAccountId': 'dx5qm9s0eb',
 'createdAt': '2018-11-27T19:50:06.035Z',
 'notifiedAt': '2018-11-27T19:50:06.708Z',
 'eventName': 'checklist.create',
 'input': {'sourcePropertyId': 'Mw67Y5oCxJ',
  'title': 'Test one off maintenance',
  'taskGroups': [{'sourceTaskGroupId': 'apst',
    'title': 'One and only task group title',
    'verificationRequired': True,
    'tasks': [{'sourceTaskId': 'apst1',
      'label': 'Glue the arms on the mannequins'},
     {'sourceTaskId': 'apst2',
      'label': 'Poke the real live bear with a stick'},
     {'sourceTaskId': 'apst3', 'label': "Don't think of an elephant"}]}],
  'description': "I'm just seeing if I can make a checklist and assign it to myself.",
  'checklistId': '5bfd9feeb9b081656f57c582'},
 'results': [{'checklistId': '5bfd9feeb9b081656f57c582',
   'title': 'Test one off maintenance',
   'description': "I'm just seeing if I can make a checklist and assign it to myself.",
   'taskGroupsCount': 1,
   'tasksCount': 3,
   'verificationRequiredCount': 1,
   'taskGroups': [{'verificationRequired': True,
     'title': 'One and only task group title',
     'sourceTaskGroupId': 'apst',
     'tasks': [{'label': 'Glue the arms on the mannequins',
       'sourceTaskId': 'apst1'},
      {'label': 'Poke the real live bear with a stick',
       'sourceTaskId': 'apst2'},
      {'label': "Don't think of an elephant", 'sourceTaskId': 'apst3'}]}]}]}

CHECKLIST_UPDATE_HOOK = {'clientRequestId': 'OKKN539',
 'apiRequestId': '5bfdb2dab9b08183eb57c5a8',
 'targetAccountId': 'dx5qm9s0eb',
 'createdAt': '2018-11-27T21:10:50.831Z',
 'notifiedAt': '2018-11-27T21:10:51.762Z',
 'eventName': 'checklist.update',
 'input': {'checklistId': '5bfd9feeb9b081656f57c582',
  'changes': {'taskGroups': [{'title': 'One and only task group title',
     'verificationRequired': True,
     'tasks': [{'sourceTaskId': 'apst1',
       'label': 'Glue the eyeballs on the dolls'},
      {'sourceTaskId': 'apst2',
       'label': 'Poke the real, live, UNCAGED bear with a stick'},
      {'sourceTaskId': 'apst3', 'label': "Don't think of an elephant"},
      {'sourceTaskId': 'apst4', 'label': 'Win a hotdog eating contest'}]}]}},
 'results': [{'checklistId': '5bfd9feeb9b081656f57c582',
   'title': 'Test one off maintenance',
   'description': "I'm just seeing if I can make a checklist and assign it to myself.",
   'taskGroupsCount': 1,
   'tasksCount': 4,
   'verificationRequiredCount': 1,
   'taskGroups': [{'verificationRequired': True,
     'title': 'One and only task group title',
     'tasks': [{'label': 'Glue the eyeballs on the dolls',
       'sourceTaskId': 'apst1'},
      {'label': 'Poke the real, live, UNCAGED bear with a stick',
       'sourceTaskId': 'apst2'},
      {'label': "Don't think of an elephant", 'sourceTaskId': 'apst3'},
      {'label': 'Win a hotdog eating contest', 'sourceTaskId': 'apst4'}]}]}]}


ONE_OFF_CREATE_MISSING_OBJECT_ERROR_WEBHOOK = {'clientRequestId': '6BV28NW',
 'apiRequestId': '5c211f6b9228c68fd2ccc47d',
 'targetAccountId': 'dx5qm9s0eb',
 'createdAt': '2018-12-24T18:03:23.527Z',
 'notifiedAt': '2018-12-24T18:03:24.655Z',
 'eventName': 'jobRequest.create',
 'input': {'title': 'Drop off bottle of wine',
  'message': 'The bottle wine is waiting at the store and has been paid for. Please give them order number 123 to pick it up.',
  'receiveUpdates': True,
  'time': {'type': 'flexible',
   'startTime': '2018-12-25T18:00:00Z',
   'durationInHours': 1,
   'endTime': '2018-12-26T03:00:00Z'},
  'property': {'sourcePropertyId': 'Mw67Y5oCxJ'},
  'checklists': [{'checklistId': '5c211f6b9228c64724ccc47b'}],
  'serviceProviders': [{'email': 'mmckay@stayd.com'}],
  'jobRequestId': '5c211f6b9228c64075ccc47e'},
 'results': [{'error': 'Invalid response from Parse. Expecting status 200 and received: 400 - Body: '}]}


ONE_OFF_CREATE_SERVER_ERROR_WEBHOOK = {'clientRequestId': '6BV28NW',
 'apiRequestId': '5c211f6b9228c68fd2ccc47d',
 'targetAccountId': 'dx5qm9s0eb',
 'createdAt': '2018-12-24T18:03:23.527Z',
 'notifiedAt': '2018-12-24T18:03:24.655Z',
 'eventName': 'jobRequest.create',
 'input': {'title': 'Drop off bottle of wine',
  'message': 'The bottle wine is waiting at the store and has been paid for. Please give them order number 123 to pick it up.',
  'receiveUpdates': True,
  'time': {'type': 'flexible',
   'startTime': '2018-12-25T18:00:00Z',
   'durationInHours': 1,
   'endTime': '2018-12-26T03:00:00Z'},
  'property': {'sourcePropertyId': 'Mw67Y5oCxJ'},
  'checklists': [{'checklistId': '5c211f6b9228c64724ccc47b'}],
  'serviceProviders': [{'email': 'mmckay@stayd.com'}],
  'jobRequestId': '5c211f6b9228c64075ccc47e'},
 'results': [{'error': 'Invalid response from Parse. Expecting status 200 and received: 503 - Body: '}]}

SAME_ONE_OFF_WORKS_THIS_TIME = {'clientRequestId': 'KPLUJVQ',
 'apiRequestId': '5c2514dd28a48047248b2945',
 'targetAccountId': 'dx5qm9s0eb',
 'createdAt': '2018-12-27T18:07:25.749Z',
 'notifiedAt': '2018-12-27T18:07:28.061Z',
 'eventName': 'jobRequest.create',
 'input': {'title': 'Drop off bottle of wine',
  'message': 'The bottle wine is waiting at the store and has been paid for. Please give them order number 123 to pick it up.',
  'receiveUpdates': True,
  'time': {'type': 'flexible',
   'startTime': '2018-12-25T18:00:00Z',
   'durationInHours': 1,
   'endTime': '2018-12-26T03:00:00Z'},
  'property': {'sourcePropertyId': 'Mw67Y5oCxJ'},
  'checklists': [{'checklistId': '5c211f6b9228c64724ccc47b'}],
  'serviceProviders': [{'email': 'mmckay@stayd.com'}],
  'jobRequestId': '5c2514dd28a480fca78b2946'},
 'results': [{'jobRequestId': '5c2514dd28a480fca78b2946',
   'receiveUpdates': True,
   'time': {'type': 'flexible',
    'startTime': '2018-12-25T18:00:00.000Z',
    'endTime': '2018-12-26T03:00:00.000Z',
    'durationInHours': 1},
   'property': {'objectId': 'Mw67Y5oCxJ',
    'title': '144 Steuben St #603 Jersey City, NJ',
    'note': None,
    'pictureUrl': 'dx5qm9s0ebJvKYqOMNOabgWIdoC380YW',
    'timeZone': 'America/New_York',
    'address': {'apt': '',
     'city': 'Jersey City',
     'country': 'United States',
     'state': 'NJ',
     'street': '144 Steuben Street Apt #603',
     'zip': '07302',
     'AddressArray': ['144 Steuben Street Apt #603',
      'Jersey City NJ 07302',
      'United States']},
    'location': [-74.0395728, 40.71945059999999],
    'numOfBedrooms': 3,
    'numOfBeds': 5,
    'numOfBathroom': None,
    'type': 'apartment',
    'detailsInformation': '-There is a washer/dryer room on every floor of the building. \n-They are all available to be used. \n-They are coin operated and cost around $2 a load in quarters. \n-After exiting the apartment turn right and walk all the way down the hall. The laundry room is located just before Staircase B and will be on your left.\n\nSMS or call 646-713-0582 with any questions.\n',
    'detailsAccess': 'If you are entering the building from Steuben St use the code 1988 to enter the building.\nWalk forward and turn right.\nEnter stairwell "A WEST," it is located to the right of the elevator.\nTake 4 steps forward and turn left.\nThe lockboxes are on the wall.\nThe main lockbox for Unit 603 is labeled 36 and the code is 2016.\n\nThe backup lockbox is on the 6th floor of stairwell "A WEST" is labeled 36B and the code is 3346.\n\nIf a key is missing please head over to 243 Montgomery St and retrieve a duplicate from the keybox. The keybox is just above the mailboxes after entering the building. The code to the keybox is 2347.\n',
    'detailsGarbage': '-Directly opposite the building entrance is a door at the end of the hallway with a small glass window. \n-This door leads to an outside trash area.\n-The code to open the door is 14403.\n-Please make sure all trash bags are tied before disposing of them.',
    'detailsParking': "There is no parking on-site. We don't recommend using street parking. It is illegal to park for over 2 hours almost everywhere in Jersey City, so you might get a ticket if you park in the street. You may use parking meters for a short while, but the time allowed to park at a meter is limited as well. Please pay attention to street signs as we are not responsible for tickets.\n\nOptions for parking:\n\nEdison Parkfast at 155 Montgomery St. - $20/night\nLM Gotham at 129 Montgomery St. - $23/night\nThe Morgan Propark America at 160 Morgan St. - $26/night\nWhere to park to unload luggage:\n\nThe best option is to briefly park in front of the building for only a few minutes while you unload\nIf you need a little extra time you may park on the curb in the driveway to the three garage doors that are 50 feet (16 meters) to the right of the building front door\nBoth of these options are technically against the parking rules, so make sure your blinkers are on and keep an eye on your car",
    'detailsWifiName': None,
    'detailsWifiPassword': None,
    'detailsWifiDescription': None,
    'otherAttributes': [],
    'sourcePropertyId': 'Mw67Y5oCxJ'},
   'checklists': [{'checklistId': '5c211f6b9228c64724ccc47b'}],
   'offeredPriceCurrency': 'USD',
   'message': 'The bottle wine is waiting at the store and has been paid for. Please give them order number 123 to pick it up.',
   'sourceBookingId': None,
   'serviceProviders': [{'email': 'mmckay@stayd.com'}]}]}

BOOKING_CREATE_WEBHOOK = {
  "clientRequestId": "24RFL15",
  "apiRequestId": "5c34def0aec7990d420cdbdd",
  "targetAccountId": "dx5qm9s0eb",
  "createdAt": "2019-01-08T17:33:36.697Z",
  "notifiedAt": "2019-01-08T17:33:37.144Z",
  "eventName": "booking.create",
  "results": [
    {
      "bookingId": "5c34def0aec7992cff0cdbde",
      "sourceBookingId": "HMPCH5RE8D",
      "startDate": "2019-02-15T21:00:00.000Z",
      "endDate": "2019-02-19T16:00:00.000Z",
      "title": "Reservation for Melinda Johnson",
      "guestDetails": [
        {
          "firstName": "Melinda",
          "lastName": "Johnson",
          "_id": "5c34def093e40b1ac429f098",
          "id": "5c34def093e40b1ac429f098"
        }
      ],
      "numberOfGuests": 1,
      "tags": []
    }
  ]
}

ERROR_BOOKING_CREATE_WEBHOOK = {
  "clientRequestId": "FV19AIQ",
  "apiRequestId": "5c375dac2d7458bef6673034",
  "targetAccountId": "dx5qm9s0eb",
  "createdAt": "2019-01-10T14:58:52.247Z",
  "notifiedAt": "2019-01-10T14:58:53.718Z",
  "eventName": "booking.create",
  "input": {
    "sourcePropertyId": "ux6RSieEjS",
    "sourceBookingId": "HMT995WC3P",
    "startDate": "2019-02-08T21:00:00Z",
    "endDate": "2019-02-10T16:00:00Z",
    "title": "Reservation for Artika Williams",
    "numberOfGuests": 1,
    "guestDetails": [
      {
        "sourceId": "104955957",
        "firstName": "Artika",
        "lastName": "Williams"
      }
    ],
    "bookingId": "5c375dac2d7458cfab673035"
  },
  "results": [
    {
      "error": "Parameters validation error! (NodeID: 31c40ced612e)"
    }
  ]
}

MISSING_SERVICE_PROVIDER = {
  "clientRequestId": "2F84NB1",
  "apiRequestId": "5cc7a8566b8fdf9858422f1f",
  "targetAccountId": "dx5qm9s0eb",
  "createdAt": "2019-04-30T01:43:50.586Z",
  "notifiedAt": "2019-04-30T01:43:52.806Z",
  "eventName": "jobRequest.create",
  "input": {
    "title": "organize apartments",
    "receiveUpdates": True,
    "time": {
      "type": "fixed",
      "startTime": "2019-04-30T18:00:00Z",
      "durationInHours": 6
    },
    "property": {
      "sourcePropertyId": "Lr5NbEAmk4"
    },
    "checklists": [
      {
        "checklistId": "5cc7a8566b8fdf719d422f1d"
      }
    ],
    "serviceProviders": [
      {
        "email": "leeciemartine@icloud.com"
      }
    ],
    "jobRequestId": "5cc7a8566b8fdff1ab422f20"
  },
  "results": [
    {
      "error": "Could not find service providers with the following emails: [\"leeciemartine@icloud.com\"]"
    }
  ]
}

TASK_UPDATED = {'clientRequestId': 'legacyRequest_5cdb3fddac75c90049c17aa6',
 'apiRequestId': '5cdaf5ba898e99866393f897',
 'targetAccountId': 'dx5qm9s0eb',
 'createdAt': '2019-05-14T22:23:25.791Z',
 'notifiedAt': '2019-05-14T22:23:28.249Z',
 'eventName': 'jobRequest.taskUpdated',
 'input': {'jobRequestId': '5cdaf5ba898e99009693f898',
  'propertyId': 'Pfd9vHaA0t',
  'sourcePropertyId': 'Pfd9vHaA0t',
  'original': {'problems': [],
   'steps': [{'tasks': [{'done': True,
       'doneAt': {'__type': 'Date', 'iso': '2019-05-14T18:30:26.252Z'},
       'note': 'Get apartments fully ready for guests (check',
       'sourceTaskId': 'BK1BU6C1'},
      {'done': True,
       'doneAt': {'__type': 'Date', 'iso': '2019-05-14T22:21:36.651Z'},
       'note': 'Get closets ready and labeled.',
       'sourceTaskId': 'BK1BU6C2'}],
     'isComplete': False,
     'incompleteTaskCount': 0,
     'problems': [],
     'title': 'Tasks',
     'isVerificationDone': False,
     'isVerificationNeeded': True,
     'verificationPictures': [],
     'sourceTaskGroupId': 'BK1BU6C'}],
   'jobSteps': [{'description': 'FINALIZING APARYMENTS',
     'totalStepCount': 1,
     'doneStepCount': 0,
     'doneVerificationPicturesCount': 0,
     'doneVerificationCount': 0,
     'totalVerificationCount': 1,
     'title': 'FINALIZING APARYMENTS',
     'type': 'standard',
     'totalTaskCount': 2,
     'objectId': '5cdaf5b6898e99ca0693f892',
     'doneTaskCount': 2,
     'steps': [{'tasks': [{'done': True,
         'doneAt': {'__type': 'Date', 'iso': '2019-05-14T18:30:26.252Z'},
         'note': 'Get apartments fully ready for guests (check',
         'sourceTaskId': 'BK1BU6C1'},
        {'done': True,
         'doneAt': {'__type': 'Date', 'iso': '2019-05-14T22:21:36.651Z'},
         'note': 'Get closets ready and labeled.',
         'sourceTaskId': 'BK1BU6C2'}],
       'isComplete': False,
       'incompleteTaskCount': 0,
       'problems': [],
       'title': 'Tasks',
       'isVerificationDone': False,
       'isVerificationNeeded': True,
       'verificationPictures': [],
       'sourceTaskGroupId': 'BK1BU6C'}]}],
   'actualStartTime': {'__type': 'Date', 'iso': '2019-05-14T18:30:25.397Z'},
   'actualEndTime': None,
   'endLat': None,
   'endLng': None,
   'startGeoPoint': {'__type': 'GeoPoint',
    'latitude': 33.422434039403655,
    'longitude': -111.91925299273518},
   'stepDoneCount': 0,
   'problemCount': 0,
   'taskDoneCount': 2,
   'verificationDoneCount': 0,
   'hostId': 'dx5qm9s0eb',
   'status': 2,
   'ownerRole': 'o_CnIU5Is7iddoKt1X',
   'propertyRole': 'p_CAml29N8nF1zZRKn',
   'createdAt': '2019-05-14T17:07:08.657Z',
   'updatedAt': '2019-05-14T22:21:43.242Z',
   'cleanerAtCheckinLoc': False,
   'ACL': {'role:o_CnIU5Is7iddoKt1X': {'read': True},
    'role:p_CAml29N8nF1zZRKn': {'read': True},
    'O3Tfuga8xT': {'read': True, 'write': True}},
   'objectId': '6J9nRJA1cS'},
  'updated': {'problems': [],
   'steps': [{'tasks': [{'done': True,
       'doneAt': {'__type': 'Date', 'iso': '2019-05-14T18:30:26.252Z'},
       'note': 'Get apartments fully ready for guests (check',
       'sourceTaskId': 'BK1BU6C1'},
      {'done': True,
       'doneAt': {'__type': 'Date', 'iso': '2019-05-14T22:21:36.651Z'},
       'note': 'Get closets ready and labeled.',
       'sourceTaskId': 'BK1BU6C2'}],
     'isComplete': True,
     'incompleteTaskCount': 0,
     'problems': [],
     'title': 'Tasks',
     'isVerificationDone': True,
     'isVerificationNeeded': True,
     'verificationPictures': ['O3Tfuga8xThwP6XTg7bkrHwzNhl5G2jt'],
     'sourceTaskGroupId': 'BK1BU6C'}],
   'jobSteps': [{'description': 'FINALIZING APARYMENTS',
     'totalStepCount': 1,
     'doneStepCount': 0,
     'doneVerificationPicturesCount': 0,
     'doneVerificationCount': 0,
     'totalVerificationCount': 1,
     'title': 'FINALIZING APARYMENTS',
     'type': 'standard',
     'totalTaskCount': 2,
     'objectId': '5cdaf5b6898e99ca0693f892',
     'doneTaskCount': 2,
     'steps': [{'tasks': [{'done': True,
         'doneAt': {'__type': 'Date', 'iso': '2019-05-14T18:30:26.252Z'},
         'note': 'Get apartments fully ready for guests (check',
         'sourceTaskId': 'BK1BU6C1'},
        {'done': True,
         'doneAt': {'__type': 'Date', 'iso': '2019-05-14T22:21:36.651Z'},
         'note': 'Get closets ready and labeled.',
         'sourceTaskId': 'BK1BU6C2'}],
       'isComplete': True,
       'incompleteTaskCount': 0,
       'problems': [],
       'title': 'Tasks',
       'isVerificationDone': True,
       'isVerificationNeeded': True,
       'verificationPictures': ['O3Tfuga8xThwP6XTg7bkrHwzNhl5G2jt'],
       'sourceTaskGroupId': 'BK1BU6C'}]}],
   'actualStartTime': {'__type': 'Date', 'iso': '2019-05-14T18:30:25.397Z'},
   'actualEndTime': None,
   'endLat': None,
   'endLng': None,
   'startGeoPoint': {'__type': 'GeoPoint',
    'latitude': 33.422434039403655,
    'longitude': -111.91925299273518},
   'stepDoneCount': 1,
   'problemCount': 0,
   'taskDoneCount': 3,
   'verificationDoneCount': 1,
   'hostId': 'dx5qm9s0eb',
   'status': 2,
   'ownerRole': 'o_CnIU5Is7iddoKt1X',
   'propertyRole': 'p_CAml29N8nF1zZRKn',
   'createdAt': '2019-05-14T17:07:08.657Z',
   'updatedAt': '2019-05-14T22:23:24.931Z',
   'cleanerAtCheckinLoc': False,
   'ACL': {'role:o_CnIU5Is7iddoKt1X': {'read': True},
    'role:p_CAml29N8nF1zZRKn': {'read': True},
    'O3Tfuga8xT': {'read': True, 'write': True}},
   'objectId': '6J9nRJA1cS',
   '__type': 'Object',
   'className': 'JobProgress'},
  'serviceProvider': {'name': 'Alicia Martinez',
   'email': 'leecieem@gmail.com'}},
 'results': [{'jobRequestId': '5cdaf5ba898e99009693f898',
   'checklists': [{'checklistId': '5cdaf5b6898e99ca0693f892',
     'taskGroupsCount': 1,
     'tasksCount': 2,
     'verificationRequiredCount': 1,
     'taskGroupsDoneCount': 0,
     'tasksDoneCount': 2,
     'verificationDoneCount': 0,
     'taskGroups': [{'taskGroupId': None,
       'note': None,
       'verificationPictures': ['https://res.cloudinary.com/dnsuxxqz1/image/upload/app/O3Tfuga8xThwP6XTg7bkrHwzNhl5G2jt.jpg'],
       'tasks': [{'taskId': None,
         'doneAt': {'__type': 'Date', 'iso': '2019-05-14T18:30:26.252Z'},
         'done': True},
        {'taskId': None,
         'doneAt': {'__type': 'Date', 'iso': '2019-05-14T22:21:36.651Z'},
         'done': True}]}]}],
   'propertyId': 'Pfd9vHaA0t',
   'sourcePropertyId': 'Pfd9vHaA0t',
   'serviceProvider': {'name': 'Alicia Martinez',
    'email': 'leecieem@gmail.com'}}]}

PROBLEM_REPORTED = {'clientRequestId': '5d0010555a947b2fc2d1b8d3',
 'apiRequestId': '5cffe19414b48a338d6f1fcd',
 'targetAccountId': 'dx5qm9s0eb',
 'createdAt': '2019-06-11T20:34:29.216Z',
 'notifiedAt': '2019-06-11T20:34:29.632Z',
 'eventName': 'jobRequest.problemReported',
 'results': [{'jobRequestId': '5cffe19414b48ac5b66f1fce',
   'problems': [{'problemId': '5cfff0dac27abf0b34ca6dce',
     'note': "doesn't show channels",
     'pictures': ['https://res.cloudinary.com/dnsuxxqz1/image/upload/app/hBme0JEoESpgaHTcjeD14XyamFQIMhhN.jpg'],
     'reportedAt': '2019-06-11T18:20:08.808Z',
     'severity': 0,
     'propertyId': 'HECFSlBxOn',
     'sourcePropertyId': 'HECFSlBxOn',
     'serviceProvider': {'name': 'Angela F ',
      'email': 'nikolagirl@yahoo.com'}},
    {'problemId': '5cffff24c27abf56deca75a6',
     'note': 'the apartment has an awful smell',
     'pictures': [],
     'reportedAt': '2019-06-11T19:21:07.802Z',
     'severity': 0,
     'propertyId': 'HECFSlBxOn',
     'sourcePropertyId': 'HECFSlBxOn',
     'serviceProvider': {'name': 'Angela F ',
      'email': 'nikolagirl@yahoo.com'}},
    {'problemId': '5d00105483dddd2e76e493b6',
     'note': "mirror off track,couldn't figure out how to get it on. ",
     'pictures': [],
     'reportedAt': '2019-06-11T20:34:29.413Z',
     'severity': 0,
     'propertyId': 'HECFSlBxOn',
     'sourcePropertyId': 'HECFSlBxOn',
     'serviceProvider': {'name': 'Angela F ',
      'email': 'nikolagirl@yahoo.com'}}]}]}
