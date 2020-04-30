from datetime import timedelta

from commands.models import background_command
from work.models.work import Work
from work.models.message import (
    MessageSender, Message, NEVER_STARTED, NEVER_COMPLETED, EMAIL)
from util.timezone import now, tz_dt_to_str


def abandoned(nnow=None):
  nnow = nnow or now()
  yesterday = nnow.date() - timedelta(days=1)
  return Work.objects.filter(
      completed_at__isnull=True, canceled_at__isnull=True,
      created_at__gte=nnow - timedelta(days=31),
      offered_start_time__date__lte=yesterday).order_by('pk').select_related(
          'cleaning', 'oneoff', 'repeatwork', 'inspection')


@background_command
def handle_abandoned_background(
    nnow=None, properly_api=None, scheduling_api=None, message_sender=None):
  nnow = nnow or now()
  message_sender = message_sender or MessageSender()
  for work in abandoned(nnow=nnow):
    work = work.get_child_class_instance()
    alerts_email = work.get_rental().building.alerts_email
    accepted_text = ''
    if work.accepted_by:
      accepted_text = 'Accepted by: {}\n'.format(work.accepted_by.name)
    content = '{}\n\n{}At: {}\nWhen: {}'.format(
        work.keys_url(), accepted_text, work.get_rental().nickname,
        tz_dt_to_str(work.offered_start_time))
    if not work.started_at:
      work.cancel(
          'Abandoned. Never started.', api=properly_api,
          scheduling_api=scheduling_api)
      message_sender.send(Message.objects.create(
          to=alerts_email, reason=NEVER_STARTED, kind=EMAIL,
          subject=NEVER_STARTED, content=content, work=work,
          when=nnow))
    else:
      if not Message.objects.filter(
          reason=NEVER_COMPLETED, work=work).exists():
        message_sender.send(Message.objects.create(
            to=alerts_email, reason=NEVER_COMPLETED, kind=EMAIL,
            subject=NEVER_COMPLETED, content=content, work=work,
            when=nnow))
