""" This verify_id_ui.py is all about VAs verifying guest IDs. """
from datetime import datetime
import re

from id_verify.models import Submission, ID_TYPE_CHOICES, post_check_id_steps
from util.timezone import now


def handle_id_verify_list_post_or_problem(
    post, who_handled, front, syncer=None, has_is_voip=None):
  problem = None
  for key in post.keys():
    found_id = re.compile(r'submission_(\d+)').match(key)
    if found_id:
      submission_id = int(found_id.groups()[0])
      submission = Submission.objects.get(pk=submission_id)
      submission.id_matches_res = _boolean_helper(
          post, submission_id, '_id_matches_res')
      if submission.id_matches_res is None:
        continue
      if submission.reservation.we_assume_cc_risk():
        submission.cc_matches_id = _boolean_helper(
            post, submission_id, '_cc_matches_id')
        submission.cc_matches_payment = _boolean_helper(
            post, submission_id, '_cc_matches_payment')
        if submission.cc_matches_id is None:
          continue
        if submission.cc_matches_payment is None:
          continue

      submission.checked_by = who_handled
      submission.checked_at = now()

      if not any([
          submission.id_matches_res is False,
          submission.cc_matches_id is False,
          submission.cc_matches_payment is False]):
        if submission.background_check_required():
          id_type = _value_helper(post, submission_id, '_id_type')
          if not id_type:
            return (
                'I need to know what type of ID this is for the background '
                'check')
          if id_type not in [item[0] for item in ID_TYPE_CHOICES]:
            raise Exception('{} isnt a valid id type'.format(id_type))
          submission.id_type = id_type
          legal_name = _value_helper(post, submission_id, '_legal_name')
          if legal_name:
            submission.legal_name = legal_name
        birthday = _value_helper(post, submission_id, '_birthday')
        if birthday:
          # You can set a date field to a string like '1967-02-21' and the
          # object will save correctly, but you don't want to do that because
          # then all the post_save functions get a submission with a string for
          # a birthday.
          submission.birthday = datetime.strptime(birthday, '%Y-%m-%d').date()
        positive_reviews_valid_format = True
        positive_reviews = None
        try:
          positive_reviews = _int_helper(
              post, submission_id, '_positive_reviews')
        except ValueError:
          positive_reviews_valid_format = False
        submission.has_negative_reviews = _boolean_helper(
            post, submission_id, '_has_negative_reviews')
        submission.positive_reviews = positive_reviews
        submission.booking_for_themself = _boolean_helper(
            post, submission_id, '_booking_for_themself')
        submission.explained_trip = _boolean_helper(
            post, submission_id, '_explained_trip')
        submission.lives_nearby = _boolean_helper(
            post, submission_id, '_lives_nearby')
      if submission.all_good():
        missing = _mandatory_field_problem(
            submission, positive_reviews_valid_format, positive_reviews,
            birthday)
        if missing:
          return missing
      submission.save(has_is_voip=has_is_voip, syncer=syncer)
      post_check_id_steps(submission.pk, front, syncer=syncer)
  return problem


def _value_helper(post, submission_id, key_suffix):
  value_key = '{}{}'.format(submission_id, key_suffix)
  return post.get(value_key, None)


def _boolean_helper(post, submission_id, key_suffix):
  value = _value_helper(post, submission_id, key_suffix)
  if value == 'yes':
    return True
  elif value == 'no':
    return False


def _int_helper(post, submission_id, key_suffix):
  value = _value_helper(post, submission_id, key_suffix)
  if value:
    return int(value)


def _mandatory_field_problem(
    submission, positive_reviews_valid_format, positive_reviews, birthday):
  if submission.has_negative_reviews is None:
    return (
        'I need to know whether or not the guest has negative reviews '
        'for the risk score')
  if not positive_reviews_valid_format:
    return 'The positive review count should be a number'
  if positive_reviews is None:
    return 'I need to know the positive review count for the risk score'
  if submission.booking_for_themself is None:
    return (
        'I need to know whether or not the guest is booking for '
        'themself\'s for the risk score')
  if submission.explained_trip is None:
    return (
        'I need to know whether or not the guest explained the reason '
        'for their trip for the risk score')
  if submission.lives_nearby is None:
    return (
        'I need to know whether or not the guest lives nearby for the '
        'risk score')
  if birthday is None:
    return 'I need to know the guest\'s birthday for the risk score'
  if submission.background_check_required():
    if not submission.birthday:
      return (
          'I need to know when they were born for the background check')
    elif not submission.legal_name:
      return (
          'I need to know their legal name from their ID for the '
          'background check')
