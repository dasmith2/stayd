from django import template
from django.template import loader

from util.money import readable_money as actual_readable_money
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


@register.simple_tag(name='round')
def do_round(value, places=0):
  return round(value, places)


@register.filter
def readable_money(num):
  return actual_readable_money(num)
