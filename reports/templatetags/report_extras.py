from django import template
from django.contrib.humanize.templatetags.humanize import intcomma


register = template.Library()


@register.filter
def currency(dollars):
  if dollars is None:
    return ''
  dollars = round(float(dollars), 2)
  return "${}{}".format(intcomma(int(dollars)), ("%0.2f" % dollars)[-3:])


@register.filter
def currency_no_cents(dollars):
  if dollars is None:
    return ''
  dollars = round(float(dollars), 2)
  return "${}".format(intcomma(int(dollars)))
