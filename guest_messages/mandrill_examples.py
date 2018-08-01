# Mandrill(...).
SEND_RESULT = [{
    'email': 'dave@stayd.com',
    'status': 'sent',
    '_id': 'bcf869ff1c864858bba7035068b62ae7',
    'reject_reason': None}]


# Mandrill(...).messages.info(send_result[0]['_id'])
SUCCESSFUL_VERIFY = {
    'ts': 1533150162,
    '_id': 'bcf869ff1c864858bba7035068b62ae7',
    'state': 'sent',
    'subject': 'Hello subject line',
    'email': 'dave@stayd.com',
    'tags': [],
    'opens': 0,
    'clicks': 0,
    'smtp_events': [{
        'ts': 1533150162,
        'type': 'sent',
        'diag': '250 2.0.0 OK 1533150162 a63-v6si4342792ywc.311 - gsmtp',
        'source_ip': '198.2.134.29',
        'destination_ip': '108.177.122.26',
        'size': 49283}],
    'resends': [],
    'sender': 'guests@staydmail.com',
    'template': 'my-first-template',
    'opens_detail': [],
    'clicks_detail': []}
