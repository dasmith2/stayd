from django import template
from django.contrib.humanize.templatetags.humanize import intcomma
from django.utils.safestring import mark_safe
from djmoney.money import Money


register = template.Library()


@register.filter(name='has_group')
def has_group(user, group_name):
  return user.is_superuser or user.groups.filter(name=group_name).exists()


@register.filter(name='can_see_guests')
def can_see_guests(user):
  return has_group(user, 'virtual_host')


@register.filter
def currency(dollars):
  if dollars is None:
    return ''
  if isinstance(dollars, Money):
    dollars = dollars.amount
  dollars = round(dollars, 2)
  with_cents = '${}{}'.format(intcomma(int(dollars)), ('%0.2f' % dollars)[-3:])
  return with_cents.replace('.00', '')


@register.filter
def currency_no_cents(dollars):
  if dollars is None:
    return ''
  dollars = round(float(dollars), 2)
  return "${}".format(intcomma(int(dollars)))


@register.filter
def pretty_yes_or_no(yes_or_no):
  if yes_or_no:
    return mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="True">')
  return mark_safe('<img src="/static/admin/img/icon-no.svg" alt="False">')


@register.simple_tag
def key(*text_color_text_color_etc):
  to_return = ['<div class="key">']
  i = 0
  while i * 2 < len(text_color_text_color_etc):
    text = text_color_text_color_etc[i * 2]
    color = text_color_text_color_etc[i * 2 + 1]
    to_return.append((
        '<span><div class="color" style="background-color: #{}"></div>'
        '{}</span>').format(color, text))
    i += 1
  to_return.append('</div>')

  return mark_safe(''.join(to_return))
