import json

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from guesty.models import RawEvent


@csrf_exempt
def guesty_webhook(request, event_name):
  send_mail(
      'We received a {} webhook!'.format(event_name),
      json.dumps(data), 'heroku@stayd.com',
      ['dave@stayd.com'], fail_silently=False)
  data = JSONParser().parse(request)
  RawEvent.objects.create(json=json.dumps(data), event_name=event_name)
  return HttpResponse('Ok')
