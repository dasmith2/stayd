# flake8: noqa

BAD_SEND = {'_error': {'status': 400,
  'title': 'Bad request',
  'message': 'The request contains an invalid resource',
  'details': ['+1972505434581 is an invalid phone handle.']}}

INVALID_PHONE = {'_error': {'status': 400,
  'title': 'Bad request',
  'message': 'The request contains an invalid resource',
  'details': ['+54 9 11 3181 6877  is an invalid phone handle.']}}

INVALID_EMAIL =  {'_error': {'status': 400,
  'title': 'Bad request',
  'message': 'The request contains an invalid resource',
  'details': ['Edison is an invalid email handle.']}}

SENT_MESSAGE = {'conversation_reference': 'a9a593b843df5f00b77166516cb15028@frontapp.com',
 'message_uid': 'a9a593b843df5f00b77166516cb15028',
 'status': 'accepted'}

MESSAGE = {'_links': {'self': 'https://api2.frontapp.com/messages/msg_1hpktpx',
  'related': {'conversation': 'https://api2.frontapp.com/conversations/cnv_pi8dfl'}}, 
 'id': 'msg_1hpktpx',
 'type': 'sms',
 'is_inbound': False,
 'created_at': 1527709281.783,
 'blurb': 'Hello Venus',
 'body': '<div>Hello Venus</div>',
 'text': 'Hello Venus',
 'metadata': {},
 'author': None,
 'recipients': [{'_links': {'related': {'contact': 'https://api2.frontapp.com/contacts/crd_53g9zd'}},
   'handle': '+16468671894',
   'role': 'from'},
  {'_links': {'related': {'contact': 'https://api2.frontapp.com/contacts/crd_72m2w5'}},
   'handle': '+19176084623',
   'role': 'to'}],
 'attachments': []}


MESSAGE_WITH_ERROR = {
 '_links': {'self': 'https://api2.frontapp.com/messages/msg_1o61ccd',
   'related': {'conversation':
     'https://api2.frontapp.com/conversations/cnv_x48nvh'}},
 'id': 'msg_1o61ccd',
 'type': 'sms',
 'is_inbound': False,
 'created_at': 1531939974.464,
 'blurb': 'Hello world',
 'body': '<div>Hello world</div>',
 'text': 'Hello world',
 'is_draft': True,
 'error_type': 'twilio_invalid_to',
 'metadata': {},
 'author': None,
 'recipients': [
  {'_links': {'related': {'contact':
       'https://api2.frontapp.com/contacts/crd_53g9zd'}},
   'handle': '+16468671894',
   'role': 'from'},
  {'_links': {'related': {'contact': None}},
   'handle': '5491131816877',
   'role': 'to'}],
 'attachments': []}


CONVERSATION = {'_links': {'self': 'https://api2.frontapp.com/conversations/cnv_pi8dfl',
  'related': {'events': 'https://api2.frontapp.com/conversations/cnv_pi8dfl/events',
   'followers': 'https://api2.frontapp.com/conversations/cnv_pi8dfl/followers',
   'messages': 'https://api2.frontapp.com/conversations/cnv_pi8dfl/messages',
   'comments': 'https://api2.frontapp.com/conversations/cnv_pi8dfl/comments',
   'inboxes': 'https://api2.frontapp.com/conversations/cnv_pi8dfl/inboxes'}},
 'id': 'cnv_pi8dfl',
 'subject': '',
 'status': 'archived',
 'assignee': None,
 'recipient': {'_links': {'related': {'contact': 'https://api2.frontapp.com/contacts/crd_72m2w5'}},
  'handle': '+19176084623',
  'role': 'from'},
 'tags': [{'_links': {'self': 'https://api2.frontapp.com/tags/tag_15ecp',
    'related': {'conversations': 'https://api2.frontapp.com/tags/tag_15ecp/conversations',
     'owner': 'https://api2.frontapp.com/teams/tim_13nd'}},
   'id': 'tag_15ecp',
   'name': 'Unanswered- 10 mins',
   'is_private': False}],
 'last_message': {'_links': {'self': 'https://api2.frontapp.com/messages/msg_1hpktpx',
   'related': {'conversation': 'https://api2.frontapp.com/conversations/cnv_pi8dfl'}},
  'id': 'msg_1hpktpx',
  'type': 'sms',
  'is_inbound': False,
  'created_at': 1527709281.783,
  'blurb': 'Hello Venus',
  'body': '<div>Hello Venus</div>',
  'text': 'Hello Venus',
  'metadata': {},
  'author': None,
  'recipients': [{'_links': {'related': {'contact': 'https://api2.frontapp.com/contacts/crd_53g9zd'}},
    'handle': '+16468671894',
    'role': 'from'},
   {'_links': {'related': {'contact': 'https://api2.frontapp.com/contacts/crd_72m2w5'}},
    'handle': '+19176084623',
    'role': 'to'}],
  'attachments': []},
 'created_at': 1522442509.8,
 'is_private': False}

