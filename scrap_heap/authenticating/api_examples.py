# flake8: noqa Yep, ran it on myself.

curl --header 'Content-Type: application/json' \
     --header 'Authorization: Bearer API_KEY_ENDING_IN_32F' \
     --request POST \
     --data '{'firstName': 'David', 'lastName': 'Smith', 'dob': '04-11-1981', 'email': 'dave@stayd.com', 'middleName': None, 'ssn': None, 'address': None, 'city': None, 'state': None, 'zipCode': None}' \
     https://api-v3.authenticating.com/user/create

{'userAccessCode':'58c8cdfc-b8c6-48fc-befa-9be865b7e06a'}

curl --header 'Content-Type: application/json' \
     --header 'Authorization: Bearer LBAHIY32GAYEW243KE4R9T3XPVHUCOK6ENYC6JTSIFZUK32F' \
     --request POST \
     --data '{'userAccessCode': '0e8d53e0-b54a-4734-bda4-2412c1b9a5f8'}' \
     https://api-v3.authenticating.com/user/getTestResult
Returned:
{
  'user': {
    'userAccessCode': '0e8d53e0-b54a-4734-bda4-2412c1b9a5f8',
    'firstName': 'THOMAS',
    'middleName': None,
    'lastName': 'BERG',
    'birthday': '1992-02-10T00:00:00.000Z',
    'year': '1992',
    'month': '02',
    'day': '10',
    'email': 'dave@hihoward.com',
    'phone': None,
    'address': None,
    'city': None,
    'state': None,
    'zipCode': None,
    'country': None,
    'street': None,
    'province': None,
    'buildingNumber': None
  },
  'contactProof': {
    'verifiedPhone': None,
    'verifiedEmail': None
  },
  'socialProof': {
    'successfulLogin': None
  },
  'photoProof': {
    'score': None
  },
  'identityProof': {
    'numQuestions': None,
    'score': None,
    'status': None
  },
  'backgroundCheck': {
    'hasCriminalRecord': False
  },
  'idVerification': {
    'status': 'PASS',
    'description': 'The data from the front and the back match strongly.'
  },
  'company': {
    'companyName': 'Master Matchmakers',
    'companyId': '9e9a1ec0-4606-4fc4-b965-fb0b69bb2984'
  },
  'scannedUser': {
    'City': 'LONG IS CITY',
    'Class': 'D',
    'CountryShort': 'USA',
    'DateOfBirth': '02-10-92',
    'DateOfBirth4': '02-10-1992',
    'DocType': 'MOB_NEW-YORK_11 (DUAL SCAN)',
    'Endorsements': 'NONE',
    'ExpirationDate': '02-10-24',
    'ExpirationDate4': '02-10-2024',
    'Eyes': 'HAZ',
    'FatherName': '',
    'Fee': '',
    'Hair': '',
    'Height': '509',
    'Id': '495357030',
    'IdCountry': 'United States',
    'IssueDate': '05-02-19',
    'IssueDate4': '05-02-2019',
    'NameFirst': 'THOMAS',
    'NameLast': 'BERG',
    'NameMiddle': '',
    'Sex': 'M',
    'State': 'NY',
    'Zip': '11101',
    'license': '495357030',
    'CardType': 'DRIVER LICENSE',
    'DocumentDetectedName': 'New York',
    'DocumentDetectedNameShort': 'NY',
    'DocumentVerificationConfidenceRating': 100,
    'IsAddressCorrected': False,
    'IsAddressVerified': False,
    'IsBarcodeRead': True,
    'IsIDVerified': True,
    'IsOcrRead': True,
    'TemplateType': 'DL',
    'Address': '4441 PURVES ST 2302'
  },
  'passportData': None,
  'professionalLicense': [],
  'education': [],
  'employment': [],
  'consent': {
    'is_report_checked': 1,
    'background_check_disclosure_accepted': 1
  }
}
