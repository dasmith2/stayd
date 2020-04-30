from django import forms
from django.contrib import admin

from typeform.models import TypeForm, RawEvent
from util.admin import ModelAdmin


@admin.register(RawEvent)
class ResponseAdmin(ModelAdmin):
  list_display = ('created_at', 'handled_at', 'typeform', 'response')
  list_select_related = ('typeform', 'response')


class TypeFormForm(forms.ModelForm):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields['title'].disabled = True

  class Meta:
    fields = ('title', 'typeform_id', 'active',)
    model = TypeForm


@admin.register(TypeForm)
class TypeFormAdmin(ModelAdmin):
  form = TypeFormForm

  list_display = ('title', 'typeform_id', 'active')
