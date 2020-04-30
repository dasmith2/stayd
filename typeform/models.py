import json

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import reverse

from errors.models import log_error
from typeform.api import API
from util.background import background
from util.random_string import get_new_random_string
from util.rm_old import RmOldManager
from util.signals import post_sync
from util.timezone import now
from util.webhook import Webhook


class TypeFormManager(models.Manager):
  def get_from_data(self, response_data):
    definition = response_data['definition']
    typeform_id = definition['id']
    typeform = self.filter(typeform_id=typeform_id).first()
    if not typeform:
      typeform = TypeForm(typeform_id=typeform_id)
    if typeform.title != definition['title']:
      typeform.title = definition['title']
      typeform.save()

    for field_data in definition['fields']:
      Question.objects.get_from_data(typeform, field_data)

    return typeform


class TypeForm(models.Model):
  typeform_id = models.CharField(unique=True, max_length=200, help_text=(
      'If the url of the form is https://stayd.typeform.com/to/BxaVCy then '
      'the id is BxaVCy'))
  title = models.CharField(max_length=200, blank=True, null=True, help_text=(
      'This automatically gets set to the title from typeform.com when we '
      'get the first form response.'))
  active = models.BooleanField(default=True, help_text=(
      'Whether or not you want to keep getting responses to this form.'))
  webhook_tag = models.CharField(
      max_length=20, default=get_new_random_string, help_text=(
          'You need to supply a unique string to create a webhook.'))
  webhook_tag_created = models.DateTimeField(null=True, blank=True, help_text=(
      'If the webhook was created, when?'))

  objects = TypeFormManager()

  def ensure_webhook(self, api=None):
    api = api or API()
    if self.active and not self.webhook_tag_created:
      url = settings.THIS_SERVERS_BASE_URL + reverse('typeform_webhook')
      api.set_webhook(self.typeform_id, self.webhook_tag, url)
      self.webhook_tag_created = now()
    elif not self.active and self.webhook_tag_created:
      api.delete_webhook(self.typeform_id, self.webhook_tag)
      self.webhook_tag_created = None
    self.save()

  def __repr__(self):
    return '<TypeForm {}: {}>'.format(self.pk, self.title)


@receiver(post_save, sender=TypeForm)
def post_save(sender, instance, *args, **kwargs):
  if settings.PROD:
    ensure_webhook_background(instance)


@background
def ensure_webhook_background(typeform):
  typeform.ensure_webhook()


class QuestionManager(models.Manager):
  def get_from_data(self, typeform, field_data):
    id = field_data['id']
    question = self.filter(question_id=id, typeform=typeform).first()
    if not question:
      question = Question(question_id=id, typeform=typeform)
    if question.title != field_data['title']:
      question.title = field_data['title']
      question.save()
    return question


class Question(models.Model):
  question_id = models.CharField(unique=True, max_length=200, help_text=(
      'This comes from typeform.com'))
  typeform = models.ForeignKey(TypeForm, on_delete=models.CASCADE)
  title = models.TextField()

  objects = QuestionManager()


class ResponseManager(models.Manager):
  def get_from_data(self, typeform, response_data):
    response = Response.objects.filter(token=response_data['token']).first()
    if not response:
      response = Response(token=response_data['token'])
    response.typeform = typeform
    if 'calculated' in response_data:
      response.score = response_data['calculated']['score']
    response.save()

    for key, value in response_data.get('hidden', {}).items():
      existing = HiddenField.objects.filter(response=response, key=key).first()
      if existing:
        existing.value = value
        existing.save()
      else:
        HiddenField.objects.create(response=response, key=key, value=value)

    for answer_data in response_data['answers']:
      Answer.objects.get_from_data(response, answer_data)

    return response


class Response(models.Model):
  typeform = models.ForeignKey(TypeForm, on_delete=models.PROTECT)
  # This used to be a UUID field but then one time we got a webhook with token
  # dga46xmlt01d0xsfylcdgcdxd77wjyl7
  token = models.CharField(unique=True, max_length=64)
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  score = models.PositiveIntegerField(null=True, blank=True, help_text=(
      'Forms can have score calculations on typeform.com'))

  objects = ResponseManager()

  def __repr__(self):
    return '<Response {}: {} {}>'.format(
        self.pk, self.created_at.date(), self.typeform.title)

  def get_hidden_lookup(self):
    return dict(
        (hidden.key, hidden.value) for hidden in self.hiddenfield_set.all())

  def print_q_and_a(self):
    for answer in self.answer_set.all():
      print('{} -> {}'.format(answer.question.title, answer.get_answer()))

  def admin_url(self):
    return reverse('see_response', kwargs={'pk': self.pk})

  def get_answer(self, *title_contains_list):
    answers = self.answer_set.all()
    for contains in title_contains_list:
      answers = answers.filter(question__title__icontains=contains)
    answers = list(answers)
    if len(answers) != 1:
      raise Exception(
          'Found {} answers for {}'.format(
              len(answers), title_contains_list))
    return answers[0].get_answer()


class HiddenField(models.Model):
  """ Typeform allows you to embed hidden fields which you populate from the
  query string. At the moment we use them to store the channel_id
  of cleaning inspections. """
  response = models.ForeignKey(Response, on_delete=models.CASCADE)
  key = models.CharField(max_length=200)
  value = models.CharField(max_length=200)


class AnswerManager(models.Manager):
  def get_from_data(self, response, answer_data):
    to_return = []
    answer_type = answer_data['type']
    single_answer = answer_data[answer_type]
    answer_values = [single_answer]
    if answer_type in ('file_url', 'phone_number'):
      answer_type = STRING_ANSWER
    elif answer_type == 'choice':
      answer_values = [single_answer['label']]
      answer_type = STRING_ANSWER
    elif answer_type == 'choices':
      answer_values = [label for label in answer_data['choices']['labels']]
      answer_type = STRING_ANSWER

    question = Question.objects.get(question_id=answer_data['field']['id'])
    missing_answers = set(answer_values)

    existing_answers = Answer.objects.filter(
        response=response, question=question).select_related('question')
    for answer in existing_answers:
      if answer.get_answer() in answer_values:
        missing_answers.remove(answer.get_answer())
        to_return.append(answer)
      else:
        answer.delete()

    for answer_value in missing_answers:
      new_answer = Answer(response=response, question=question)
      new_answer.set_answer(answer_value, answer_type)
      new_answer.save()
      to_return.append(new_answer)

    return to_return


STRING_ANSWER = 'text'
BOOLEAN_ANSWER = 'boolean'
INT_ANSWER = 'number'
ANSWER_TYPE_CHOICES = (
    (STRING_ANSWER, STRING_ANSWER),
    (BOOLEAN_ANSWER, BOOLEAN_ANSWER),
    (INT_ANSWER, INT_ANSWER))


class Answer(models.Model):
  response = models.ForeignKey(Response, on_delete=models.CASCADE)
  question = models.ForeignKey(Question, on_delete=models.CASCADE)
  str_answer = models.TextField(null=True, blank=True, help_text=(
      'If the answer is a string it goes here.'))
  int_answer = models.IntegerField(null=True, blank=True, help_text=(
      'If the answer is an integer it goes here.'))
  bool_answer = models.BooleanField(null=True, blank=True, help_text=(
      'If the answer is a boolean it goes here.'))
  answer_type = models.CharField(max_length=50, choices=ANSWER_TYPE_CHOICES)

  objects = AnswerManager()

  def __repr__(self):
    return '<Answer {}: {} {}>'.format(
        self.pk, self.question.title[:30], str(self.get_answer())[:30])

  def set_answer(self, answer, answer_type):
    self.answer_type = answer_type
    if answer_type == INT_ANSWER:
      self.int_answer = answer
    elif answer_type == BOOLEAN_ANSWER:
      self.bool_answer = answer
    else:
      self.str_answer = str(answer)
      if answer_type != STRING_ANSWER:
        subject = 'Not sure what to do with a {} answer type'.format(
            answer_type)
        if settings.TEST:
          raise Exception(subject)
        log_error(
            subject, 'Defaulting to string. Question {}, answer {}'.format(
                self.question.pk, answer))

  def is_img(self):
    answer = self.get_answer()
    return self.answer_type == STRING_ANSWER and (
        answer.find('https://api.typeform.com/responses/files') >= 0)

  def get_answer(self):
    if self.answer_type == INT_ANSWER:
      return self.int_answer
    if self.answer_type == BOOLEAN_ANSWER:
      return self.bool_answer
    return self.str_answer


class RawEvent(Webhook):
  typeform = models.ForeignKey(
      TypeForm, on_delete=models.CASCADE, null=True, blank=True)
  response = models.ForeignKey(
      Response, on_delete=models.CASCADE, null=True, blank=True)

  objects = RmOldManager()

  def handle(self, **kwargs):
    """ **kwargs is in case you want to pass in a mock that's specific to an
    app. For instance, typeform -> manual payment passes in a `work` message
    sender. """
    data = json.loads(self.json)
    if data['event_type'] == 'form_response':
      response_data = data['form_response']
      self.typeform = TypeForm.objects.get_from_data(response_data)
      self.response = Response.objects.get_from_data(
          self.typeform, response_data)
      self.save()
      post_sync.send(sender=Response, instance=self.response, **kwargs)
    self.handled_at = now()
    self.save()
