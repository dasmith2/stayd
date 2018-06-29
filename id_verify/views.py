import os

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, reverse

from id_verify.models import Submission
from id_verify.s3 import S3
from util.fake_admin import admin_context


def view_image(request, file_name):
  if not os.path.exists(file_name):  # More or less always.
    S3().download(file_name)
  f = open(file_name, "rb")
  read = f.read()
  f.close()
  os.remove(file_name)
  return HttpResponse(read, content_type="image/jpeg")


def verify_id(request):
  if request.method == 'POST':
    Submission.objects.create(
        photo_file_name=request.POST['destination_file_name'],
        email=request.POST['email'])
    return redirect(reverse(thanks_for_verifying_id))
  return render(request, 'verify_id.html')


def thanks_for_verifying_id(request):
  return render(request, 'thanks_for_verify.html')


def id_verification_list(request):
  context = admin_context(
      'Stayd ID verification',
      submissions=Submission.objects.filter(resized=True))
  return render(request, 'id_verification_list.html', context=context)


def sign_s3(request):
  file_type = request.GET.get('file_type', '')
  if not file_type:
    return HttpResponse(
        'You have to include a file_type parameter.', status=400)

  destination_file_name = Submission.objects.get_destination_file_name(
      file_type)
  presigned_post = _get_presigned_post(destination_file_name, file_type)

  return JsonResponse({
      'presigned_post': presigned_post,
      'destination_file_name': destination_file_name})


def _get_presigned_post(file_name, file_type):
  return S3().generate_presigned_post(
      Bucket=settings.S3_BUCKET_NAME,
      Key=file_name,
      Fields={"Content-Type": file_type},
      Conditions=[{"Content-Type": file_type}],
      ExpiresIn=3600)
