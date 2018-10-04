from django import template
from django.template import loader

from util.urls import url_with as actual_url_with


register = template.Library()


@register.simple_tag
def do_building(building, include_caret=False):
  return loader.get_template(
      'dashboard_building.html').render(
          {'building': building, 'include_caret': include_caret})


@register.simple_tag
def url_with(request_get_full_path, key, value):
  return actual_url_with(request_get_full_path, key, value)
