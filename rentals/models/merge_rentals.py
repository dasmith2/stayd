from util.signals import post_sync
from util.table import Table, Cell


def clean_up_dupe_rentals_table(rentals, show_keep_this_one=True):
  headers = [
      'Keep this one', 'Nickname', 'Apartment', 'Full address', 'Keys ID',
      'Guesty ID', 'Is active']
  if not show_keep_this_one:
    headers = headers[1:]
  table = Table(headers)
  for rental in rentals:
    guesty_id = rental.guestyrental_or_none and rental.guestyrental.guesty_id
    action_cell = Cell(
        additional_attrs={'data-rental-id': rental.pk},
        classes=['keep_rental_cell'])
    cells = [
        action_cell,
        rental.nickname, rental.apartment, rental.full_address, rental.pk,
        guesty_id, rental.is_active]
    if not show_keep_this_one:
      cells = cells[1:]
    table.create_row(cells)
  return table


def merge_rentals(keep_rental, discard_rental):
  # See Rental._meta.related_objects
  for reservation in discard_rental.reservation_set.all():
    reservation.rental = keep_rental
    reservation.save()
    post_sync.send(sender=reservation.__class__, instance=reservation)
  for monthly_expense in discard_rental.monthlyexpense_set.all():
    monthly_expense.rental = keep_rental
    monthly_expense.save()
  discard_rental.stats_set.all().delete()

  if discard_rental.properlyrental_or_none:
    keep_properly_rental = keep_rental.properlyrental_or_none
    discard_properly_rental = discard_rental.properlyrental
    if keep_properly_rental:
      keep_properly_rental.properly_property_id = (
          keep_properly_rental.properly_property_id or (
              discard_properly_rental.properly_property_id))
      keep_properly_rental.source_property_id = (
          keep_properly_rental.source_property_id or (
              discard_properly_rental.source_property_id))
      keep_properly_rental.clean_co = (
          keep_properly_rental.clean_co or (
              discard_properly_rental.clean_co))
      keep_properly_rental.cleaning_flat_rate = (
          keep_properly_rental.cleaning_flat_rate or (
              discard_properly_rental.cleaning_flat_rate))
      if discard_properly_rental.cleaningconfig_or_none:
        discard_config = (
            discard_properly_rental.cleaningconfig)
        if keep_properly_rental.cleaningconfig_or_none:
          keep_config = keep_properly_rental.cleaningconfig
          keep_config.checklist_id = keep_config.checklist_id or (
              discard_config.checklist_id)
          keep_config.inspection_checklist_id = (
              keep_config.inspection_checklist_id or (
                  discard_config.inspection_checklist_id))
          keep_config.cleaning_duration = (
              keep_config.cleaning_duration or (
                  discard_config.cleaning_duration))
          keep_config.properly_rental = keep_config.properly_rental or (
              discard_config.properly_rental)
          keep_config.message = keep_config.message or (
              discard_config.message)
          keep_config.save()
          discard_config.delete()
        else:
          discard_config.properly_rental = keep_properly_rental
          discard_config.save()
      for checklist in discard_properly_rental.maintenancechecklist_set.all():
        checklist.properly_rental = keep_properly_rental
        checklist.save()
      for repeat_config in (
          discard_properly_rental.repeatconfig_set.all()):
        repeat_config.properly_rental = keep_properly_rental
        repeat_config.save()
      for one_off in discard_properly_rental.oneoff_set.all():
        one_off.properly_rental = keep_properly_rental
        one_off.save()
      discard_properly_rental.delete()
      keep_properly_rental.save()
    else:
      discard_properly_rental.rental = keep_rental
      discard_properly_rental.save()
  for cleaning in discard_rental.cleaning_set.all():
    cleaning.rental = keep_rental
    cleaning.save()
  for maintenance in discard_rental.maintenance_set.all():
    maintenance.rental = keep_rental
    maintenance.save()
  for ticket in discard_rental.ticket_set.all():
    ticket.rental = keep_rental
    ticket.save()
  discard_rental.refresh_from_db()
  discard_rental.delete()
