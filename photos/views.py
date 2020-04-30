from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render

from photos.s3 import S3
from photos.file_types import (
    suffix_from_file_type, content_type_from_file_name)
from util.permission import can_groups
from util.random_string import random_string


@login_required
@can_groups('id_verify', 'virtual_host')
def view_sensitive_image(request, file_name):
  img_bytes = S3(sensitive=True).image_bytes(file_name)
  if img_bytes:
    return HttpResponse(
        img_bytes, content_type=content_type_from_file_name(file_name))
  return Http404()


def photo_demo(request):
  """ This simple page is what I'm using to get photo management working. """
  return render(request, 'photo_demo.html', {})


def sign_s3_sensitive(request):
  return sign_s3(request, sensitive=True)


def sign_s3_public(request):
  return sign_s3(request, sensitive=False)


def sign_s3(request, sensitive):
  """ The user is about to try to upload a photo directly to S3. We gotta
  sign it and say where it goes. """
  file_type = request.GET.get('file_type', '')
  if not file_type:
    return HttpResponse(
        'You have to include a file_type parameter.', status=400)
  suffix = suffix_from_file_type(file_type)
  if not suffix:
    # If you're figuring out what to do with an exception like this,
    # go modify set_up_file_upload in
    # id_verify/templates/verify_my_id_script.html
    raise Exception(
        'Not sure what to do with file_type {}'.format(file_type))

  destination_file_name = '{}.{}'.format(random_string(), suffix)
  presigned_post = S3(sensitive=sensitive).generate_presigned_post(
      destination_file_name, file_type)

  return JsonResponse({
      'presigned_post': presigned_post,
      'destination_file_name': destination_file_name})
