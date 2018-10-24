# flake8: noqa:E402 module level import not at top of file
"""
I'm afraid that apscheduler appears to be basically undocumented for how we're
using it. I'm just following the directions on
https://devcenter.heroku.com/articles/clock-processes-python
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

from util.temp_send_email_background import send_email

sched = BlockingScheduler()


@sched.scheduled_job('interval', minutes=10)
def timed_job():
  send_email('10 minute email')


@sched.scheduled_job('cron', hour=0)
def scheduled_job0():
  send_email('hour=0 email')


@sched.scheduled_job('cron', hour=1)
def scheduled_job1():
  send_email('hour=1 email')


@sched.scheduled_job('cron', hour=2)
def scheduled_job2():
  send_email('hour=2 email')


@sched.scheduled_job('cron', hour=3)
def scheduled_job3():
  send_email('hour=3 email')


@sched.scheduled_job('cron', hour=4)
def scheduled_job4():
  send_email('hour=4 email')


@sched.scheduled_job('cron', hour=5)
def scheduled_job5():
  send_email('hour=5 email')


@sched.scheduled_job('cron', hour=6)
def scheduled_job6():
  send_email('hour=6 email')


@sched.scheduled_job('cron', hour=7)
def scheduled_job7():
  send_email('hour=7 email')


@sched.scheduled_job('cron', hour=8)
def scheduled_job8():
  send_email('hour=8 email')


@sched.scheduled_job('cron', hour=9)
def scheduled_job9():
  send_email('hour=9 email')


@sched.scheduled_job('cron', hour=10)
def scheduled_job10():
  send_email('hour=10 email')


@sched.scheduled_job('cron', hour=11)
def scheduled_job11():
  send_email('hour=11 email')


@sched.scheduled_job('cron', hour=12)
def scheduled_job12():
  send_email('hour=12 email')


@sched.scheduled_job('cron', hour=13)
def scheduled_job13():
  send_email('hour=13 email')


@sched.scheduled_job('cron', hour=14)
def scheduled_job14():
  send_email('hour=14 email')


@sched.scheduled_job('cron', hour=15)
def scheduled_job15():
  send_email('hour=15 email')


@sched.scheduled_job('cron', hour=16)
def scheduled_job16():
  send_email('hour=16 email')


@sched.scheduled_job('cron', hour=17)
def scheduled_job17():
  send_email('hour=17 email')


@sched.scheduled_job('cron', hour=18)
def scheduled_job18():
  send_email('hour=18 email')


@sched.scheduled_job('cron', hour=19)
def scheduled_job19():
  send_email('hour=19 email')


@sched.scheduled_job('cron', hour=20)
def scheduled_job20():
  send_email('hour=20 email')


@sched.scheduled_job('cron', hour=21)
def scheduled_job21():
  send_email('hour=21 email')


@sched.scheduled_job('cron', hour=22)
def scheduled_job22():
  send_email('hour=22 email')


@sched.scheduled_job('cron', hour=23)
def scheduled_job23():
  send_email('hour=23 email')


sched.start()
