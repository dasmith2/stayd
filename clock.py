"""
This file is in New York time.

You can't import background here because that causes "Functions from the
__main__ module cannot be processed by workers". But also, the clock itself
should never do any actual work. It should only kick tasks off to background
threads.

Hence, no work may be placed directly in this file. This file is strictly for
scheduling.

I'm afraid that apscheduler appears to be basically undocumented for how we're
using it. I'm just following the directions on
https://devcenter.heroku.com/articles/clock-processes-python

This file is the entire reason we have flake8 (./lint.sh) globally ignore
E402 module level import not at top of file
"""
import os

import django

# Otherwise you get django.core.exceptions.ImproperlyConfigured: Requested
# setting INSTALLED_APPS, but settings are not configured. You must either
# define the environment variable DJANGO_SETTINGS_MODULE or call
# settings.configure() before accessing settings.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stayd.settings')
django.setup()


from apscheduler.schedulers.blocking import BlockingScheduler

from commands.stayd_command import run_stayd_command, ErrorCommand
# from guest_messages.management.commands.send_guest_messages import ( Command
# as send_guest_messages_command)
sched = BlockingScheduler()


"""
@sched.scheduled_job('interval', minutes=60)
def send_guest_messages():
  run_stayd_command(send_guest_messages_command())
"""


@sched.scheduled_job('interval', minutes=5)
def send_guest_messages():
  run_stayd_command(ErrorCommand())


@sched.scheduled_job('cron', hour=12)
def scheduled_job():
  pass


sched.start()
