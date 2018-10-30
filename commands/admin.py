from django.contrib import admin

from commands.models import CommandRun
from util.timezone import get_readable_duration


@admin.register(CommandRun)
class CommandRunAdmin(admin.ModelAdmin):
  def duration(self, instance):
    if not instance.completed:
      return '-'
    return get_readable_duration(instance.completed - instance.started)

  list_display = ('command_name', 'started', 'completed', 'duration', 'error')
