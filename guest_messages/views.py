from django.http import HttpResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from guest_messages.forms import TemplateFormSet
from guest_messages.models import Template, TrackingPixel
from util.fake_admin import admin_context


TRACKING_PIXEL = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='  # noqa:E501


@login_required
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
  return render(request, 'guest_message_templates.html', context=context)


def tracking_pixel(request, tracking_pixel_id):
  TrackingPixel.objects.track(tracking_pixel_id)
  return HttpResponse(TRACKING_PIXEL, content_type='image/png')
