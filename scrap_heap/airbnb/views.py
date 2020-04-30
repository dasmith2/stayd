from io import TextIOWrapper
import sys

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import render

from airbnb.models import RawUpload
from errors.models import log_error, notify
from util.admin import admin_context
from util.permission import can_groups, ACCOUNTANT, CSV_UPLOAD


@login_required
@can_groups(ACCOUNTANT, CSV_UPLOAD)
def upload_airbnb_csv(request):
  notify(
      'dave@hihoward.com', 'upload_airbnb_csv is still being used',
      'Which is awfully surprising')
  context = admin_context('Upload Airbnb CSV')
  if request.method == 'POST':
    bytes_file = request.FILES.get('file', None)
    if bytes_file:
      csv_text = TextIOWrapper(bytes_file, encoding=request.encoding).read()
      raw = RawUpload.objects.create(text=csv_text)
      try:
        context['results'] = raw.handle()
      except Exception:
        helpful = 'https://keys.hihoward.com/see_upload/{}/'.format(
            raw.pk)
        log_error('Error handling Airbnb csv upload', helpful, sys.exc_info())
  return render(request, 'upload_airbnb_csv.html', context=context)


@login_required
@can_groups(ACCOUNTANT)
def see_airbnb_csv_upload(request, pk):
  notify(
      'dave@hihoward.com', 'see_airbnb_csv_upload is still being used',
      'Which is awfully surprising')
  raw = RawUpload.objects.filter(pk=pk).first()
  if raw:
    return HttpResponse('<pre>{}</pre>'.format(raw.text))
  return HttpResponseNotFound('RawUpload {} doesn\'t exist'.format(pk))
