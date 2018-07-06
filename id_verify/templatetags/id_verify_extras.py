from django import template
from django.template.loader import render_to_string


register = template.Library()


@register.simple_tag
def file_upload(destination_prefix, put_result, show_button):
  return render_to_string('file_upload.html', {
      'destination_prefix': destination_prefix,
      'put_result': put_result,
      'show_button': show_button})
