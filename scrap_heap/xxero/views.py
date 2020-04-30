from collections import namedtuple

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, reverse

from util.admin import admin_context
from util.permission import ACCOUNTANT, can_groups
from xxero.models.bento_2_transaction import (
    get_merchant_category_2_coconut, handle_merchant_category_2_coconut)
from xxero.models.coconuts import Coconut


@login_required
@can_groups(ACCOUNTANT)
def conflicted_coconuts(request):
  """ Here's how conflict resolution happens. First Coconut.objects.sync() gets
  called which pulls all the Coconuts for all the businesses into a master
  list. If at any point a Coconut comes back that doesn't agree with the master
  list (names the same, codes different, or visa versa), it creates a
  CoconutConflict for every Business describing what that Business thinks the
  code and name are. Then an email goes out to Seb. He goes to
  conflicted_coconut to see what everything thinks the answer is. He tweaks
  them, submits them. Coconut.objects validates his answer and pushes it out to
  Xero for each affected business. """
  just_resolved = int(request.GET.get('just_resolved', 0))
  conflicted = Coconut.objects.conflicted()
  use_conflicts = [coco for coco in conflicted if just_resolved != coco.pk]
  context = admin_context(
      'Chart of Accounts conflicts', conflicts=use_conflicts)
  return render(request, 'conflicted_coconuts.html', context=context)


@login_required
@can_groups(ACCOUNTANT)
def conflicted_coconut(request, pk):
  problems = []
  post = {}
  if request.method == 'POST':
    post = request.POST
    problems.extend(Coconut.objects.validate_resolution(request.POST))
    if not problems:
      Coconut.objects.resolve(request.POST)
      return redirect(
          reverse('conflicted_coconuts') + '?just_resolved={}'.format(pk))

  coconut = Coconut.objects.get(pk=pk)
  title = 'Conflict: {}'.format(coconut.name)
  conflicts_data = []
  ConflictData = namedtuple(
      'ConflictData', 'business_name pk name code system_coconut')
  for conflict in coconut.coconutconflict_set.all():
    business_name = conflict.business.name
    pk = conflict.pk
    name = post.get('name_{}'.format(pk), conflict.name)
    code = post.get('code_{}'.format(pk), conflict.code)
    conflicts_data.append(ConflictData(
        business_name, pk, name, code, conflict.system_coconut))

  context = admin_context(
      title, conflicts_data=conflicts_data, problems=problems)

  return render(request, 'conflicted_coconut.html', context=context)


@login_required
@can_groups(ACCOUNTANT)
def merchant_category_2_coconut(request):
  if request.method == 'POST':
    handle_merchant_category_2_coconut(request.POST)

  context = admin_context(
      'Merchant category -> coconut',
      mc2c_values=get_merchant_category_2_coconut(),
      coconuts=Coconut.objects.all())
  return render(request, 'merchant_category_2_coconut.html', context=context)
