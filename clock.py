"""
This file is in New York time.

Error reporting isn't perfect here. You can catch import errors by
python clock.py

To see the logs,

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

I'm afraid that apscheduler appears to be basically undocumented for how we're
using it. I'm just following the directions on
https://devcenter.heroku.com/articles/clock-processes-python

This file is the entire reason we have flake8 (./lint.sh) globally ignore
E402 module level import not at top of file
"""
import os
import sys

import django

# Otherwise you get django.core.exceptions.ImproperlyConfigured: Requested
# setting INSTALLED_APPS, but settings are not configured. You must either
# define the environment variable DJANGO_SETTINGS_MODULE or call
# settings.configure() before accessing settings.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stayd.settings')
django.setup()


from apscheduler.schedulers.blocking import BlockingScheduler
from guest_messages.management.commands.send_guest_messages import (
    run_send_guest_messages_background)
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


# test.sh fires this file up with --no-run so continuous integration breaks
# when this file contains import errors.
if '--no-run' not in sys.argv:
  sched.start()
