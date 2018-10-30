from commands.models import background_command

from properly.models.messages import Message


@background_command('Send 9am daily job reminders')
def send_9am_daily_job_reminders_background():
  Message.objects.send_9am_daily_job_reminders()


@background_command('Send 10 minute late cleaning notifications')
def send_10_minute_late_cleaning_notifications_background():
  Message.objects.send_10_minute_late_cleaning_notifications()


@background_command('Send 15 minute late cleaning notifications')
def send_15_minute_late_cleaning_notifications_background():
  Message.objects.send_15_minute_late_cleaning_notifications()


@background_command('Send unclaimed cleaning in lt 48 hours')
def send_unclaimed_cleaning_in_lt_48_hours_background():
  Message.objects.send_unclaimed_cleaning_in_lt_48_hours()


@background_command('Send cleaning taking too long notifications')
def send_cleaning_taking_too_long_notifications_background():
  Message.objects.send_cleaning_taking_too_long_notifications()
