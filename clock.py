"""
This is basically our cron. It's in New York time.

Error reporting isn't perfect here. Lint catches syntax errors, the deploy
process catches import errors, and as long as the functions you import and run
are decorated with @background or @background_command then any exceptions they
raise will get emailed. But there are still cracks in the system you can sneak
bugs into, such as running a @background function that's on a models.Manager.
See util/background.py for a more detailed explanation of why that fails
specifically, but the point is, it is possible to swallow errors here, so be
careful. Follow conventions. Don't get fancy.

If something fishy is going on despite all the precautions, check the logs.

heroku logs -d clock -t -a stayd-prod

You can also look in the commands/models#CommandRun table to ensure your
@background_command is running successfully.

You can't import background here because any function you decorate with it will
trigger "Functions from the __main__ module cannot be processed by workers".
So you have to import functions that are decorated with background. And they
all should be, because the clock itself should never do any actual work. It
should only kick tasks off to background threads.

Hence, no work may be placed directly in this file. This file is strictly for
scheduling.

Cron scheduling:
https://apscheduler.readthedocs.io/en/latest/modules/triggers/cron.html

Interval scheduling:
https://apscheduler.readthedocs.io/en/latest/modules/triggers/interval.html

Uh, it seems to me that interval scheduling is not very reliable. I'm looking
at a case where it went 3 hours and 8 minutes for the 1 hour interval scheduled
fix_stale, and there wasn't anything happening to block it or anything. But
that could also be our reddis provider.

This file is the entire reason we have flake8 (./lint.sh) globally ignore
E402 module level import not at top of file
"""
import os
import sys

import django

# Otherwise you get "django.core.exceptions.ImproperlyConfigured: Requested
# setting INSTALLED_APPS, but settings are not configured. You must either
# define the environment variable DJANGO_SETTINGS_MODULE or call
# settings.configure() before accessing settings."
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stayd.settings')
django.setup()


from aaircall.models import push_front_contacts_to_aircall_background
from apscheduler.schedulers.blocking import BlockingScheduler
from bgcheck.models.background_check import (
    must_cancel_daily_notification_background)
from bgcheck.models.chemail import send_chemails_background
from front.models import sync_sms_channels_background
from guest_messages.management.commands.send_guest_messages import (
    run_send_guest_messages_background)
from guesty.guesty import (
    reinstall_webhooks_background as reinstall_guesty_webhooks_background)
from id_verify.models import post_submission_steps_background
from paypal.models import (
    check_status_background as check_paypal_payout_status_background)
from photos.models import (
    clean_up_never_used, clean_up_no_longer_needed, resize_all)
from reservations.models.money import (
    alert_likely_payin_not_ideal_payin_background)
from guesty.poll_guesty import (
    poll_reservations_expecting_payment, poll_all_confirmed_within_a_month,
    poll_created_last_week, poll_reserved_reservations)
from stats.management.commands.fix_stale import run_fix_stale_background
from stripe.models import (
    sync_stripe_background, alert_unlinked_charges_background)
from util.management.commands.rm_old import run_rm_old_background
from util.management.commands.circle_back_around import (
    run_circle_back_around_background)
from work.models.abandoned import handle_abandoned_background
from work.models.cleaning import create_cleanings_in_keys_background
from work.models.inspect import schedule_inspections_background
from work.models.maintenance import clean_up_empty_maintenance_background
from work.models.repeat_work import (
    create_tickets_background as create_repeat_config_tickets_background,
    alert_should_have_but_didnt_unblock_background)
from work.models.cleaning_messages import (
    send_through_the_day_cleaning_messages_background)
from work.models.one_off import disable_old_checklists_background
from work.models.raw_event import retry_properly_webhooks_background
from work.models.ticket import email_no_sla_ticket_count_background
from work.models.ticket_scheduler import (
    schedule_background as schedule_tickets_background)
from work.models.work_message import (
    send_9am_daily_job_reminders_background,
    send_through_the_day_work_messages_background)


sched = BlockingScheduler()


@sched.scheduled_job('cron', minute=0)
def send_guest_messages():
  """ Most, if not all, of our scheduled messages get sent out on the hour. """
  run_send_guest_messages_background()


@sched.scheduled_job('cron', hour=1)
def rm_old():
  run_rm_old_background()


@sched.scheduled_job('cron', hour=2)
def sync_stripe():
  sync_stripe_background()
  alert_unlinked_charges_background()


@sched.scheduled_job('cron', hour=3)
def must_cancel_daily_notification():
  must_cancel_daily_notification_background()


@sched.scheduled_job('interval', minutes=60)
def send_chemails():
  send_chemails_background()


@sched.scheduled_job('cron', hour=4)
def sync_sms_channels():
  sync_sms_channels_background()


@sched.scheduled_job('cron', hour=5)
def disable_old_checklists():
  disable_old_checklists_background()


@sched.scheduled_job('cron', hour='3')
def push_front_contacts_to_aircall():
  # Front AND Aircall have pretty brutal rate limiting, so I've seen this take,
  # like, half an hour. Only run it in the middle of the night.
  push_front_contacts_to_aircall_background()


@sched.scheduled_job('interval', minutes=60)
def circle_back_around():
  run_circle_back_around_background()


@sched.scheduled_job('interval', minutes=60)
def check_paypal_payout_status():
  check_paypal_payout_status_background()


@sched.scheduled_job('cron', hour='1')
def photo_stuff():
  clean_up_never_used()
  clean_up_no_longer_needed()
  resize_all()


@sched.scheduled_job('interval', minutes=60)
def fix_stale():
  run_fix_stale_background()


@sched.scheduled_job('interval', minutes=60)
def poll_reservations_hourly():
  poll_reservations_expecting_payment()
  poll_reserved_reservations()


@sched.scheduled_job('cron', hour='0,9')
def poll_reservations_daily():
  poll_created_last_week()
  poll_all_confirmed_within_a_month()


@sched.scheduled_job('cron', hour=1)
def alert_likely_payin_not_ideal_payin():
  alert_likely_payin_not_ideal_payin_background()


@sched.scheduled_job('cron', hour=0)
def handle_abandoned():
  handle_abandoned_background()


@sched.scheduled_job('cron', hour='12,14')
def init_cleanings():
  create_cleanings_in_keys_background()


@sched.scheduled_job('cron', hour=1)
def clean_up_empty_maintenance():
  clean_up_empty_maintenance_background()


@sched.scheduled_job('interval', minutes=10)
def create_repeat_config_tickets():
  create_repeat_config_tickets_background()


@sched.scheduled_job('cron', hour='1,13')
def alert_should_have_but_didnt_unblock():
  alert_should_have_but_didnt_unblock_background()


@sched.scheduled_job('cron', minute=35)
def retry_properly_webhooks():
  retry_properly_webhooks_background()


@sched.scheduled_job('cron', hour='12-15', minute='10')
def schedule_inspections():
  schedule_inspections_background()


@sched.scheduled_job('cron', hour=9)
def send_9am_daily_job_reminders():
  send_9am_daily_job_reminders_background()


@sched.scheduled_job('cron', minute='0,10,20,30,40,50')
def schedule_tickets():
  schedule_tickets_background()


@sched.scheduled_job('cron', hour='9,18')
def email_no_sla_ticket_count():
  email_no_sla_ticket_count_background()


@sched.scheduled_job(
    'cron', hour='9-21', minute='0,5,10,15,20,25,30,35,40,45,50,55')
def send_through_the_day_work_messages():
  send_through_the_day_cleaning_messages_background()
  send_through_the_day_work_messages_background()


@sched.scheduled_job('cron', hour='1,13')
def reinstall_guesty_webhooks():
  reinstall_guesty_webhooks_background()


@sched.scheduled_job('cron', hour=0)
def post_submission_steps():
  post_submission_steps_background()


# test.sh fires this file up with --no-run so continuous integration breaks
# when this file contains import errors.
if '--no-run' not in sys.argv:
  sched.start()
