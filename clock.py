"""
This file is in New York time.

Error reporting isn't perfect here. Lint catches syntax errors, the deploy
process catches import errors, and as long as the functions you import and run
are decorated with @background then any exceptions they raise will get emailed.
But it's still possible to sneak errors inbetween the cracks, so be careful.

Otherwise, to see the logs,

heroku logs -d clock -t -a stayd-prod

You can also look in the commands/models#CommandRun table to ensure your
command is running successfully.

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


from apscheduler.schedulers.blocking import BlockingScheduler
from guest_messages.management.commands.send_guest_messages import (
    run_send_guest_messages_background)
from properly.models.messages import (
    send_9am_daily_job_reminders_background,
    send_10_minute_late_cleaning_notifications_background,
    send_15_minute_late_cleaning_notifications_background,
    send_unclaimed_cleaning_in_lt_48_hours_background,
    send_cleaning_taking_too_long_notifications_background)
from util.management.commands.rm_old import run_rm_old_background
from util.management.commands.circle_back_around import (
    run_circle_back_around_background)
from stats.management.commands.fix_stale import run_fix_stale_background


sched = BlockingScheduler()


@sched.scheduled_job('interval', minutes=60)
def send_guest_messages():
  run_send_guest_messages_background()


@sched.scheduled_job('cron', hour=1)
def rm_old():
  run_rm_old_background()


@sched.scheduled_job('interval', minutes=60)
def circle_back_around():
  run_circle_back_around_background()


@sched.scheduled_job('interval', minutes=60)
def fix_stale():
  run_fix_stale_background()


@sched.scheduled_job('cron', hour=9)
def send_9am_daily_job_reminders():
  send_9am_daily_job_reminders_background()


@sched.scheduled_job('cron', hour='10-14', minute='25', second='30')
def send_10_minute_late_cleaning_notifications():
  send_10_minute_late_cleaning_notifications_background()


@sched.scheduled_job('cron', hour='10-14', minute='30', second='30')
def send_15_minute_late_cleaning_notifications():
  send_15_minute_late_cleaning_notifications_background()


@sched.scheduled_job(
    'cron', hour='14-18', minute='0,15,30,45')
def send_cleaning_taking_too_long_notifications():
  send_cleaning_taking_too_long_notifications_background()


@sched.scheduled_job('cron', minute='16')
def send_unclaimed_cleaning_in_lt_48_hours():
  send_unclaimed_cleaning_in_lt_48_hours_background()


# test.sh fires this file up with --no-run so continuous integration breaks
# when this file contains import errors.
if '--no-run' not in sys.argv:
  sched.start()
