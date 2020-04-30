from django.contrib import admin

from util.admin import ModelAdmin
from va.models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(ModelAdmin):
  list_display = ['text', 'start', 'end']
  ordering = ('-start',)
