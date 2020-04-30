import csv

from django.http import HttpResponse


def csv_writer_and_response(file_name='unhelpful_generic_file_name.csv'):
  response = HttpResponse(content_type='text/csv')
  response['Content-Disposition'] = (
      'attachment; filename="{}"'.format(file_name))
  writer = csv.writer(response)
  return writer, response


def send_csv():
  raise NotImplementedError('See util.email.send_csv')
