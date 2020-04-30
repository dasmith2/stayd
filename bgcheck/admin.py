from django.contrib import admin

from bgcheck.models import DoorPerson
from util.admin import ModelAdmin


@admin.register(DoorPerson)
class DoorPersonAdmin(ModelAdmin):
  list_display = ['building', 'user']
