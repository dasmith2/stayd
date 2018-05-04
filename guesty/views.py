import json

from django.core.mail import send_mail
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from guesty.models import RawEvent


@csrf_exempt
def guesty_webhook(request, event_name):
  data_str = json.dumps(JSONParser().parse(request))

  send_mail(
      'We received a {} webhook!'.format(event_name),
      data_str, 'heroku@stayd.com',
      ['dave@stayd.com'], fail_silently=False)
  RawEvent.objects.create(json=data_str, event_name=event_name)
  return HttpResponse('Ok')
