from django.contrib import admin
from django.utils.html import format_html

from commands.models import CommandRun
from util.timezone import get_readable_duration


@admin.register(CommandRun)
class CommandRunAdmin(admin.ModelAdmin):
  def duration(self, instance):
    if not instance.completed:
      return '-'
    return get_readable_duration(instance.completed - instance.started)

  def error_link(self, instance):
    if instance.error:
      url = '/admin/errors/stayderror/{}/change/'.format(instance.error.pk)
      return format_html(
          '<a href="{url}">{msg}</a>', url=url,
          msg=instance.error.error_message[:30])
    return '-'
  error_link.short_description = 'error'

  list_display = (
      'command_name', 'started', 'completed', 'duration', 'error_link')
