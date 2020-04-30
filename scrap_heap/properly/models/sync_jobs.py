""" FINALLY properly provided a mechanism to query all existing jobs regardless
of whether they were created in the web UI or by the API. Since they are so
unreliable with webhooks, run this before, say, running nanny functions so we
don't unduly bug people.

BUT, there's a nasty, unsolvable, underlying dynamic that causes bugs
regularly. Let me set the stage. We use a SQL database. With a SQL database,
you got, like, one reservation per row in the reservation table. It's so
simple, so obvious. You want a list of reservations? Query the one and only
reservations table. The UI, the API, all of it, it all queries the same table
which is protected by unique keys and such. So you see, a SQL database is
fairly easy to keep de-normalized. The only downside to a SQL database, really,
is that it has to run on a single server at a time. You can get really far on
that, but you can't get infinitely far. SQL databases lack infinite
scalability.

If you're Google making fractions of a penny per user and you got billions of
users worldwide, you're gonna need infinite scalability. A SQL database isn't
gonna cut it. In that case, you need to spread X data in Y buckets on Z
servers. The way you do that is NoSQL. The weakness of NoSQL is, now it's not
so obvious where you go to get that list of reservations. If you aren't
careful, copies-of-things run amok. THE classic bug here is, I wrote code that
updated the objects in list A used for one purpose, but I totally forgot to
update the copies of those objects in list B used for a different purpose.
Staying on top of this is pretty much the reason NoSQL architectures require
armies of very bright engineers, IF you want to have any hope of doing a
reliable job.

There's another, stupider advantage to NoSQL: it's shiney. So if the game
you're REALLY playing is, get investor money, you might pick NoSQL just because
it looks good in a Powerpoint presentation.

You see where this is going. I discovered after asking a few pointed questions
that Properly, who accepts enormous amounts of investor capital, is built on
NoSQL. But, they lack an army of bright engineers. They have a poor testing
culture. They're all about looking impressive, but the code barely functions.
They struggle to release updates. Every update they do release is 1 step
forward, 2 steps back, bug-wise.

Therefore, this here list, the listing.cleaningJobs list, is perpetually out of
date due to bugs. One time they had a bug where the jobs in this list had
totally different IDs. One time they had a bug where this list was unaware that
several jobs had been accepted. I'm sure there will be more. (a few days later:
a bug where several jobs didn't know they'd been completed)

As long as we depend on Properly, it's accidentally our job to provide free QA
that their webhooks, the web UI, and this list are synchronized, because they
sure don't notice on their own. That's exactly their weakness. Specifically, we
have to notice and tell them when jobs fail to send webhooks, and we have to
notice and tell them when this list has out-of-date data.

The long term solution is probably to just bring all this stuff in house. It's
not THAT complicated, but it does have to be reliable and well-integrated. I
would be VERY surprised if Properly ever became reliable OR well-integrated.
"""
from datetime import timedelta
import json

from django.utils.dateparse import parse_datetime

from commands.models import background_command
from errors.models import log_error
from work.api import API
from work.models.one_off import OneOff
from work.models.rental import ProperlyRental
from work.models.work import Work
from work.models.worker import Worker
from util.html_status_codes import ServerError
from util.timezone import tz_dt_to_tz_dt, now


@background_command
def sync_properly_jobs_background():
  trigger_sync_jobs(now() - timedelta(days=7), now() + timedelta(days=7))


def trigger_sync_jobs(from_datetime, to_datetime, api=None):
  api = api or API()
  from_date_str = tz_dt_to_tz_dt(
      from_datetime, tz_str='UTC').isoformat().replace('+00:00', 'Z')
  to_date_str = tz_dt_to_tz_dt(
      to_datetime, tz_str='UTC').isoformat().replace('+00:00', 'Z')
  data = {'filters': {'dateFrom': from_date_str, 'dateTo': to_date_str}}
  try:
    api.cleaning_jobs(data)
  except ServerError:
    pass  # Ugh, fine. We do this a bunch so just skip it this time I guess.


# From
# https://getproperly.atlassian.net/wiki/spaces/API/overview#ProperlyAPI-v2-listing.cleaningJobs
CREATED_STATUS = 1
ACCEPTED_STATUS = 2
CANCELLED_STATUS = 3
DECLINED_STATUS = 4
STARTED_STATUS = 5
PAUSED_STATUS = 6
FINISHED_STATUS = 7
CANCELLED_BY_SERVICE_PROVIDER_STATUS = 8


def do_sync_jobs(job_data_list, message_sender, api=None, nnow=None):
  nnow = nnow or now()
  for data in job_data_list:
    # Yep, there's, like, 1 job in sync_jobs that has an _id an no jobId.
    job_request_id = data.get('jobId', None) or data.get('_id', None)
    if not job_request_id:
      log_error(
          'Wow yeah one of these jobs doesnt have a job_request_id',
          '{}'.format(json.dumps(data, indent=2)))
      continue
    status = data['status']
    offered_start_time = parse_datetime(data['scheduledStartTime'])
    completed_at = data.get('actualEndTime', None)
    if completed_at:
      completed_at = parse_datetime(completed_at)
    started_at = data.get('actualStartTime', None)
    if started_at:
      started_at = parse_datetime(started_at)

    properly_property_id = data['propertyId']
    properly_rental = ProperlyRental.objects.filter(
        properly_property_id=properly_property_id).first()

    accepted_by = None
    worker_id = data.get('cleanerId', None)
    worker_email = data.get('cleanerEmail', None)
    if worker_email:
      accepted_by = Worker.objects.filter(email=worker_email).first()
    if accepted_by and accepted_by.worker_id != worker_id:
      accepted_by.worker_id = worker_id
      accepted_by.save()

    existing = Work.objects.filter(job_request_id=job_request_id).first()
    # One time, properly started returning multiple ids for the same job
    # depending on the source of the job, or something. So here I put
    # existing_by_fields = find_matching(offered_start_time, accepted_by,
    # rental) or something like that. But the problem was, if you had a valid
    # job for the same person at the same spot at the same time, the old
    # canceled job would match to the new job and I'd be like, "Oh this job is
    # apparently canceled." So the moral is, even when THEY mess up the IDs,
    # don't get clever and try to find objects without IDs. Down that road lies
    # insanity.
    if existing:
      existing = existing.get_child_class_instance()
      if not existing.creation_confirmed:
        existing.creation_confirmed = nnow
      existing.offered_start_time = offered_start_time
      # One time Properly had a bug where this list was unaware jobs had been
      # started or completed.
      existing.completed_at = existing.completed_at or completed_at
      existing.started_at = existing.started_at or started_at
      if status == DECLINED_STATUS:
        # This API call doesn't say who declined the job.
        pass
      elif worker_id:
        # One time, a cleaning had an error on creation but nevertheless the
        # job was accepted. So evidentally it got created. The code assumes
        # that if there's a creation_error, it didn't get created. So clear
        # this out.
        existing.creation_error = ''
      # Sigh, sometimes syncJobs is out of sync and isn't aware that a job was
      # accepted. So if we got an accepted webhook, DON'T clear out the
      # accepted_by field just because syncJobs isn't aware it was accepted.
      existing.accepted_by = existing.accepted_by or accepted_by
      existing.action_on_properly = existing.action_on_properly or bool(
          accepted_by or started_at or completed_at)
      existing.save()

      if status == CANCELLED_STATUS:
        if not existing.canceled_at:
          # Friendly note, this doesn't modify the `existing` object but it
          # does modify the database, so don't call existing.save() past here.
          existing.was_canceled(
              permanently_canceled_reason='', api=api, nnow=nnow)
      elif status == CANCELLED_BY_SERVICE_PROVIDER_STATUS:
        if not existing.canceled_at:
          existing.was_canceled_by_worker(api=api, nnow=nnow)
      elif existing.canceled_at:
        # If you get here, you probably hit a classic Properly bug. Other
        # systems are aware that a job was canceled, but this list isn't aware
        # and thinks the job is still in some earlier status. Just ignore it I
        # guess. I used to have an alert here but it wasn't helpful.
        pass
    elif properly_rental and accepted_by and status in [
        STARTED_STATUS, PAUSED_STATUS, FINISHED_STATUS]:
      # Ooo boy, we have no idea what type of work this is.
      one_off = OneOff.objects.create(
          accepted_by=accepted_by,
          job_request_id=job_request_id,
          started_at=started_at,
          accepted_at=offered_start_time,
          completed_at=completed_at,
          offered_start_time=offered_start_time,
          title='Unknown',
          message='The properly API doesn\'t tell us what this job is.',
          properly_rental=properly_rental,
          expected_duration=0)
      if one_off.workpayment_or_none:
        one_off.workpayment.on_hold_reason = (
            'This job was created in the Properly web app, so I have no idea '
            'if this was a cleaning or a one-off or what. Please verify!')
        one_off.workpayment.save()
