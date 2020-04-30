""" This verify_id_ui.py is all about guests submitting IDs for verification.
"""
from django.db.models import Q

from id_verify.models import (
    Submission, SubmissionPhoto, ID, BACK_OF_ID, CC,
    post_submission_steps_background)
from errors.models import ErrorLogger
from reservations.models import Reservation
from util.channels import THEY_ASSUME_CC_RISK_CHANNELS
from util.timezone import now


def get_url_to_create_a_checkable_submission():
  """ This is really just for development when you want to create a
  submission that will appear in the submissions list. """
  reservation = Reservation.objects.filter(
      Q(channel__in=THEY_ASSUME_CC_RISK_CHANNELS) | Q(
          cc_last_4__isnull=False),
      id_verified=False, check_out__gt=now()).first()
  if reservation:
    return reservation.verify_id_url()
  else:
    print(
        'No reservation in the database will do. Maybe set '
        'id_verified=False on a bunch or sync some.')


def reservation_from_post(post):
  if post.get('reservation_id', None):
    return Reservation.objects.filter(pk=post['reservation_id']).first()


def handle_opt_out_bgcheck(post):
  reservation = reservation_from_post(post)
  Submission.objects.create(
      reservation=reservation, opt_out_of_bgcheck=True, opt_in_email=False,
      opt_in_texts=False)


def handle_submission_post(
    post, email_sender, syncer=None, logger=ErrorLogger()):
  unique_form_id = post.get('unique_form_id', '')
  email = post.get('submit_email', '').strip()
  phone = post.get('submit_phone', '').strip()
  if unique_form_id:
    submission = Submission.objects.filter(
        unique_form_id=unique_form_id).first()
    if submission:
      submission.email = email
      submission.opt_in_email = post['opt_in_email'] == 'true'
      submission.phone = phone
      submission.opt_in_texts = post['opt_in_texts'] == 'true'
      submission.save()
      return submission
  reservation = reservation_from_post(post)
  submission = Submission.objects.create(
      query=post['query'],
      unique_form_id=unique_form_id,
      email=email,
      opt_in_email=post['opt_in_email'] == 'true',
      phone=phone,
      opt_in_texts=post['opt_in_texts'] == 'true',
      reservation=reservation)
  handle_submission_photo(post, 'id_file_upload', ID, submission)
  handle_submission_photo(post, 'cc_file_upload', CC, submission)
  handle_submission_photo(
      post, 'id_back_upload', BACK_OF_ID, submission)
  if reservation:
    post_submission_steps_background(
        submission_pk=submission.pk, syncer=syncer,
        email_sender=email_sender)
  else:
    # I used to send an alert here. But now when a reservation syncs, it
    # checks to see if there are any unmatched submissions and hooks them up
    # at that point.
    pass
  return submission


def handle_submission_photo(post, post_key, photo_type, submission, **kwargs):
  """ kwargs so I can pass in s3_override for tests """
  if post_key in post and post[post_key]:
    photo = SubmissionPhoto(
        submission=submission,
        photo_type=photo_type,
        file_name=post[post_key])
    photo.calc_and_set_keep()
    photo.save(**kwargs)
    return photo
