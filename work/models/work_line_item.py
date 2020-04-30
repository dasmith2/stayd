""" A cleaner fixes the couch. They ought to get paid extra for that cleaning.
So now we make a "Fix the couch" line item for $10 for that cleaning. These are
somewhat tested by work.tests.test_clean_co """
from django.db import models
from django import forms
from django.forms import formset_factory
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from work.models.work import Work


def get_work_line_item_lookup(works):
  """ {work pk: [wli, wli]} I use the primary key of the work to avoid type
  confusion, a.k.a. is the work the key or is the cleaning the key. This is to
  help avoid doing a separate select every time you want to know about work
  line items for a job, like in the pay service providers table. """
  lookup = {}
  for wli in WorkLineItem.objects.filter(work__in=works):
    if wli.work_id not in lookup:
      lookup[wli.work_id] = []
    lookup[wli.work_id].append(wli)
  return lookup


class WorkLineItem(models.Model):
  work = models.ForeignKey(Work, on_delete=models.CASCADE)
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')
  description = models.TextField()
  charge_sales_tax = models.BooleanField(default=True, help_text=(
      'Should we pay you sales tax? If this is for work, probably. If this '
      'is for supplies, probably not.'))


""" Form stuff is tested as part of work.tests.test_clean_co """


class WorkLineItemForm(forms.Form):
  pk = forms.IntegerField(widget=forms.HiddenInput, required=False)
  delete = forms.BooleanField(required=False)
  amount = forms.DecimalField()
  description = forms.CharField()


WorkLineItemFormSet = formset_factory(WorkLineItemForm)


def get_work_line_item_formset_data(work):
  data = {
      'li-MAX_NUM_FORMS': '',
      'li-INITIAL_FORMS': '0'}
  index = -1

  items = []
  if work:
    items = list(work.worklineitem_set.order_by('pk'))
  items += [WorkLineItem() for extra in range(2)]

  for (index, item) in enumerate(items):
    data['li-{}-pk'.format(index)] = item.pk
    data['li-{}-amount'.format(index)] = item.amount and item.amount.amount
    data['li-{}-description'.format(index)] = item.description
  data['li-TOTAL_FORMS'] = index + 1
  return data


def get_work_line_item_formset_for_work(work):
  return WorkLineItemFormSet(
      get_work_line_item_formset_data(work), prefix='li')


def get_work_line_item_formset_from_post(request_post, work):
  return WorkLineItemFormSet(request_post, prefix='li')


def save_work_line_item_formset(formset, work):
  if not formset.is_valid():
    raise Exception('only save valid formsets')
  for form in formset:
    pk = form['pk'].value()
    wli = None
    if pk:
      wli = work.worklineitem_set.filter(pk=form['pk'].value()).first()
    delete = form['delete'].value()
    amount = form['amount'].value()
    description = form['description'].value()
    if delete:
      if wli:
        wli.delete()
    elif amount or description:
      if not wli:
        wli = WorkLineItem(work=work)
      wli.amount = Money(amount, 'USD')
      wli.description = description
      wli.save()
  return get_work_line_item_formset_for_work(work)
