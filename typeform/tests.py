import json
from unittest.mock import Mock, call
from uuid import uuid4

from django.conf import settings
from django.shortcuts import reverse

from typeform.api import API
from typeform.api_examples import RESPONSE, CLEANING_INSPECTION_RESPONSE
from typeform.models import (
    RawEvent, TypeForm, Question, Response, Answer, HiddenField)
from util.tests import TestCase


def get_test_typeform(**kwargs):
  typeform_id = 'tarpfoorm'
  next_suffix = 1
  while TypeForm.objects.filter(typeform_id=typeform_id).exists():
    typeform_id += str(next_suffix)
    next_suffix += 1
  typeform = TypeForm.objects.create(
      typeform_id=kwargs.get('typeform_id', typeform_id),
      title=kwargs.get('title', 'Cleaning inspection'),
      active=kwargs.get('active', True),
      webhook_tag_created=kwargs.get('webhook_tag_created', None))
  if 'webhook_tag' in kwargs:
    typeform.webhook_tag = kwargs['webhook_tag']
    typeform.save()
  return typeform


def get_test_response(**kwargs):
  typeform = kwargs.get('typeform', None)
  if not typeform:
    typeform = get_test_typeform(**kwargs)
  return Response.objects.create(
      typeform=typeform,
      token=kwargs.get('token', uuid4()),
      score=kwargs.get('score', None))


class TypeFormTests(TestCase):
  def test_ensure_webhooks(self):
    typeform = get_test_typeform(
        webhook_tag_created=None, typeform_id='biply', webhook_tag='ABCD')

    api = Mock(spec=API)
    for i in range(2):
      typeform.ensure_webhook(api=api)

    self.assertEqual(0, len(api.delete_webhook.call_args_list))
    url = settings.THIS_SERVERS_BASE_URL + '/typeform/webhook/'
    self.assertEqual(
        [call('biply', 'ABCD', url)], api.set_webhook.call_args_list)

    typeform.active = False
    for i in range(2):
      typeform.ensure_webhook(api=api)

    self.assertEqual(1, len(api.set_webhook.call_args_list))
    self.assertEqual(
        [call('biply', 'ABCD')], api.delete_webhook.call_args_list)


class RawEventTests(TestCase):
  def test_cleaning_inspection_response(self):
    raw_event = RawEvent.objects.create(
        json=json.dumps(CLEANING_INSPECTION_RESPONSE))
    for i in range(2):
      raw_event.handle()
    self.assertTrue(raw_event.handled_at)
    self.assertEqual(1, TypeForm.objects.count())

    self.assertEqual(1, Response.objects.count())
    response = Response.objects.first()
    self.assertEqual(1, HiddenField.objects.count())

    self.assertTrue(HiddenField.objects.filter(
        response=response, key='reservation_id', value='HMRKWSFQKP').exists())

    multiple_choice_answer_objs = Answer.objects.filter(
        question__question_id='t6264wOG9nI6')
    multiple_choice_answers = (
        [answer.get_answer() for answer in multiple_choice_answer_objs])
    expected_answers = ['Any surfaces dirty']
    self.assertEqual(set(expected_answers), set(multiple_choice_answers))
    expect_file_url_answer = (
        'https://api.typeform.com/responses/files/aadaca010695016abd474be67'
        '6ec40d26bb03b39561d0a811d7f7e19152ccac1')
    got_file_url_answer = Answer.objects.get(
        question__question_id='OU3TDxVqAiRb').get_answer()
    self.assertEqual(expect_file_url_answer, got_file_url_answer)

    # As long as we're in here
    url = reverse('see_response', kwargs={'pk': response.pk})
    self.login(is_superuser=True)
    self.assert_get_contains(url, 'Rate the bathroom cleaning.')

  def test_handle_webhook_response(self):
    raw_event = RawEvent.objects.create(json=json.dumps(RESPONSE))
    for i in range(2):
      raw_event.handle()
    self.assertTrue(raw_event.handled_at)

    self.assertEqual(1, TypeForm.objects.count())
    typeform = TypeForm.objects.first()
    self.assertEqual('lT4Z3j', typeform.typeform_id)
    self.assertEqual('Webhooks example', typeform.title)
    self.assertTrue(typeform.active)

    self.assertEqual(1, Response.objects.count())
    response = Response.objects.first()
    self.assertEqual(typeform, response.typeform)
    self.assertEqual('a3a12ec67a1365927098a606107fac15', response.token)
    self.assertEqual(9, response.score)

    self.assertEqual(11, Question.objects.count())
    question = Question.objects.get(question_id='DlXFaesGBpoF')
    self.assertEqual(typeform, question.typeform)
    self.assertEqual((
        'Thanks, {{answer_60906475}}! What\'s it like where you live? Tell us '
        'in a few sentences.'), question.title)

    self.assertEqual(9, Answer.objects.count())
    answer = Answer.objects.get(question__question_id='JwWggjAKtOkA')
    self.assertEqual('Laura', answer.get_answer())
    self.assertEqual(response, answer.response)
    self.assertEqual(
        True, Answer.objects.get(
            question__question_id='gFFf3xAkJKsr').get_answer())
    self.assertEqual(
        5, Answer.objects.get(
            question__question_id='Q7M2XAwY04dW').get_answer())
