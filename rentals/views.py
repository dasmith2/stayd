from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from rentals.models import Rental
from rentals.models.merge_rentals import (
    clean_up_dupe_rentals_table, merge_rentals)
from util.admin import admin_context
from util.permission import is_superuser


@login_required
@is_superuser
def clean_up_dupe_rentals(request):
  ids = []
  ids_str = request.GET.get('ids', '')
  str_ids = list(filter(None, ids_str.split(',')))
  if str_ids:
    ids = [int(id) for id in str_ids]
  message = ''
  rentals_table = None
  show_merge_button = True
  if len(ids) == 2:
    rentals = Rental.objects.filter(pk__in=ids).order_by('pk')
    if len(rentals) == 2:
      rentals_table = clean_up_dupe_rentals_table(rentals)
      if request.method == 'POST':
        keep_rental_pk = request.POST.get('keep_rental', None)
        if keep_rental_pk:
          keep_rental_pk = int(keep_rental_pk)
          keep_rental = None
          discard_rental = None
          for rental in rentals:
            if rental.pk == keep_rental_pk:
              keep_rental = rental
            else:
              discard_rental = rental
          merge_rentals(keep_rental, discard_rental)
          message = 'Merged!'
          rentals = rentals.filter(pk=keep_rental_pk)
          rentals_table = clean_up_dupe_rentals_table(
              rentals, show_keep_this_one=False)
          show_merge_button = False
        else:
          message = 'Select the rental you wish to keep.'
    else:
      message = 'At least one of these rentals doesn\'t exist.'
  else:
    message = (
        'I expect precisely 2 rentals at a time. You specified '
        '{} of them.').format(len(ids))
  context = admin_context(
      'Clean up duplicate rentals', message=message,
      rentals_table=rentals_table, ids_str=ids_str,
      show_merge_button=show_merge_button)
  return render(request, 'clean_up_dupe_rentals.html', context=context)
