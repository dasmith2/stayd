from django.shortcuts import render

from guest_messages.forms import TemplateFormSet
from guest_messages.models import Template
from util.fake_admin import admin_context


def edit_guest_message_templates(request):
  if request.method == 'POST':
    formset = TemplateFormSet(request.POST)
    if formset.is_valid():
      formset.save()
      formset = TemplateFormSet(queryset=Template.objects.all())
  else:
    formset = TemplateFormSet(queryset=Template.objects.all())
  context = admin_context(
      'Guest SMS templates',
      formset=formset)
  return render(request, 'admin/guest_message_templates.html', context=context)
