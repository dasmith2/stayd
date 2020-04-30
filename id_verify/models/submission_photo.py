from datetime import timedelta

from django.db import models

from id_verify.cc_blanker import CCBlanker
from id_verify.models.submission import Submission, ID, CC, BACK_OF_ID
from front.models import Front
from guest_messages.models.message import INVALID_IMAGE_UPLOAD
from guest_messages.models.sms import SMS
from photos.models import Photo
from util.timezone import now


PHOTO_TYPE_CHOICES = (
    (ID, ID),
    (CC, CC),
    (BACK_OF_ID, BACK_OF_ID))


class SubmissionPhoto(Photo):
  submission = models.ForeignKey(Submission, on_delete=models.CASCADE)
  photo_type = models.CharField(max_length=10, choices=PHOTO_TYPE_CHOICES)

  def explain_why_no_need_for_photo(self, nnow=None):
    nnow = nnow or now()
    if self.submission.reservation:
      if self.submission.reservation.we_assume_cc_risk():
        expires_at = self.submission.reservation.check_out + timedelta(days=93)
        if expires_at < nnow:
          return 'The guest can no longer charge back the credit card.'
      else:
        expires_at = self.submission.reservation.check_out + timedelta(days=5)
        if expires_at < nnow:
          return 'We would have noticed any damage by now.'
    else:
      expires_at = self.submission.created_at + timedelta(days=2)
      if expires_at < nnow:
        return 'No matching reservation after 2 days'
    return ''

  def calc_and_set_keep(self, **kwargs):
    if self.submission.reservation:
      if self.submission.reservation.we_assume_cc_risk():
        self.keep_until = self.submission.reservation.check_out + timedelta(
            days=93)
      else:
        self.keep_until = self.submission.reservation.check_out + timedelta(
            days=5)
    else:
      self.keep_until = self.submission.created_at + timedelta(days=2)
    self.keep_forever = False

  def sensitive(self):
    return True

  def post_resize(self):
    all_resized = True
    for photo in self.submission.submissionphoto_set.all():
      all_resized = all_resized and photo.resized_at
    if all_resized:
      self.submission.resized = True
      self.submission.save()

  def notify_bad_image(self, **kwargs):
    front = kwargs.get('front', Front())
    if self.valid:
      if self.submission.reservation:
        SMS.objects.send_for_reservation_or_explain_why_not(
            self.submission.reservation.pk, INVALID_IMAGE_UPLOAD, front)
      self.valid = False
      self.save()

  def do_additional_resize_steps(
      self, input_file_name, output_file_name, **kwargs):
    if self.photo_type == CC:
      blanker = kwargs.get('blanker', None) or CCBlanker()
      blanker.blank_cc(input_file_name, output_file_name)
