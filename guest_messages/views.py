from django.http import HttpResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from guest_messages.forms import TemplateFormSet
from guest_messages.models import Template, TrackingPixel
from util.fake_admin import admin_context


TRACKING_PIXEL = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\rIDAT\x08\xd7c````\x00\x00\x00\x05\x00\x01^\xf3*:\x00\x00\x00\x00IEND\xaeB`\x82'  # noqa:E501


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
