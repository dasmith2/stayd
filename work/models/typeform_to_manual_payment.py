import re

from django.conf import settings
from django.db.models import Q
from django.dispatch import receiver
from djmoney.money import Money

from errors.models import log_error
from work.models.message import (
    Message, MessageSender, EMAIL,
    CANT_FIND_RECEIPT_BUILDING_BY_NICKNAME, CANT_FIND_RECEIPT_WORKER_BY_PHONE,
    NEW_RECEIPT)
from work.models.payment import ManualPayment
from work.models.work import Worker
from work.models.work_co import WorkCo
from work.models.work_co_worker import WorkCoWorker
from rentals.models import Building
from typeform.models import TypeForm, Response as TypeformResponse
from util.phone import numbers_only
from util.signals import post_sync
from util.timezone import now
from util.urls import keys_reverse


@receiver(post_sync, sender=TypeformResponse)
def post_sync_response_receipt(sender, instance, *args, **kwargs):
  if instance.typeform.typeform_id == get_submit_receipt_typeform_id():
    if not instance.manualpayment_or_none:
      create_manual_payment(
          instance, message_sender=kwargs.get('message_sender', None))


def get_submit_receipt_typeform_id():
  typeform = TypeForm.objects.filter(
      title__icontains='submit receipt').first()
  if typeform:
    return typeform.typeform_id
  log_error(
      'Not sure what typeform is for submitting receipts', (
          'Im looking for a TypeForm whose title contains the text '
          '"submit receipt". Because I couldnt find one I just went '
          'with the default id of aVcNg4'))
  return 'aVcNg4'


def get_responses_without_payments():
  """ When this pipeline inevitably fails, use this to find the responses that
  didn't get a successful manualpayment. """
  return TypeformResponse.objects.filter(
      typeform__typeform_id=get_submit_receipt_typeform_id(),
      manualpayment__isnull=True)


def create_manual_payment(response, message_sender=None):
  message_sender = message_sender or MessageSender()

  on_hold_reason_parts = ['Created automatically. Please verify!']
  phone = response.get_answer('phone')
  description = response.get_answer('what', 'why')
  how_much = response.get_answer('how much')
  building_nickname = response.get_answer('building')
  receipt_photo_url = response.get_answer('photo')

  worker = None
  work_co = None
  if len(phone) >= 7:
    worker = Worker.objects.filter(
        Q(phone_numbers_only__contains=numbers_only(phone)) | Q(
            email=phone)).first()
    work_co = WorkCo.objects.filter(
        Q(owner__email=phone) | Q(alerts_email=phone)).first()
  if not (worker or work_co):
    on_hold_reason_parts.append((
        'I couldn\'t find who submitted this receipt based on phone/email '
        '{}').format(phone))
  if worker:
    worker = worker.get_child_class_instance()
    if isinstance(worker, WorkCoWorker):
      work_co = worker.work_co
      worker = None

  amount = Money('0', 'USD')
  try:
    amount = Money(float(re.compile(r'[^\.\d]').sub('', how_much)), 'USD')
  except ValueError:
    on_hold_reason_parts.append(
        'The typeform response had "{}" as a dollar amount, but that doesn\'t '
        'appear to be a valid decimal number.'.format(how_much))

  building = Building.objects.filter(nickname=building_nickname).first()
  if not building:
    on_hold_reason_parts.append(
        'The typeform response mentions building "{}", but none of our '
        'buildings have that nickname.'.format(building_nickname))

  payment = ManualPayment.objects.create(
      subject=description,
      message=description,
      worker=worker,
      work_co=work_co,
      building=building,
      receipt_photo_url=receipt_photo_url,
      amount=amount,
      typeform_response=response,
      on_hold_reason=' '.join(on_hold_reason_parts),
      work_completed=now())

  if not building:
    _notify_cant_find_building(building_nickname, message_sender)
  elif not worker:
    _notify_cant_find_worker(phone, response, payment, message_sender)
  else:
    _notify_new_receipt(payment, message_sender)


def _notify_new_receipt(payment, message_sender):
  Message.objects.create_and_send_email(
      settings.ALERT_NEW_RECEIPT, NEW_RECEIPT, payment.keys_url(), None,
      message_sender=message_sender)


def _notify_cant_find_building(building_nickname, message_sender):
  content = (
      '<a href="https://admin.typeform.com/form/{}/create">'
      'This typeform</a> refers to a building with nickname {}, but none '
      'of <a href="{}">our buildings</a> actually have that '
      'nickname. The building question should use the EXACT '
      'building nicknames from keys.').format(
          get_submit_receipt_typeform_id(), building_nickname,
          keys_reverse('admin:rentals_building_changelist'))
  message_sender.send(Message.objects.create(
      to=settings.ALERT_CANT_FIGURE_OUT_RECEIPT,
      reason=CANT_FIND_RECEIPT_BUILDING_BY_NICKNAME, kind=EMAIL,
      subject=CANT_FIND_RECEIPT_BUILDING_BY_NICKNAME, content=content,
      when=now()))


def _notify_cant_find_worker(phone, response, payment, message_sender):
  content = (
      'They said their phone number was {}, but '
      'I don\'t have any <a href="{}">independent service providers</a> '
      'or <a href="{}">service providers who work for a company</a> '
      'with that phone number. You can see the complete Typeform response '
      '<a href="{}">here</a>. I did create '
      '<a href="{}">a manual payment</a> for this receipt. Somebody '
      'will have to figure out who it belongs to before we can pay '
      'it though.').format(
          phone,
          keys_reverse('admin:work_independentworker_changelist'),
          keys_reverse('admin:work_workcoworker_changelist'),
          response.admin_url(),
          payment.keys_url())
  message_sender.send(Message.objects.create(
      to=settings.ALERT_CANT_FIGURE_OUT_RECEIPT,
      reason=CANT_FIND_RECEIPT_WORKER_BY_PHONE, kind=EMAIL,
      subject=CANT_FIND_RECEIPT_WORKER_BY_PHONE, content=content, when=now()))
