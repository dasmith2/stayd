from django.http import HttpResponse

from rentals.models import Building, Rental


class Checker(object):
  def _can_view_owner(self, viewing_user, owner_id):
    return not owner_id or viewing_user.pk == owner_id

  def _can_view_building(self, viewing_user, building):
    if not building:
      return True
    return viewing_user.pk == building.owner.pk

  def _can_view_rental(self, viewing_user, rental):
    if not rental:
      return True
    return viewing_user.pk == rental.building.owner.pk

  def get_permission_problems(
      self, viewing_user, building_id=None, rental_id=None, owner_id=None):
    if viewing_user.is_staff:
      return
    if building_id and not self._can_view_building(
        viewing_user, Building.objects.get(pk=building_id)):
      return HttpResponse(
          'You don\'t have permission to view this building', status=403)
    if rental_id and not self._can_view_rental(
        viewing_user, Rental.objects.get(pk=rental_id)):
      return HttpResponse(
          'You don\'t have permission to view this rental', status=403)
    if not self._can_view_owner(viewing_user, owner_id):
      return HttpResponse(
          'You don\'t have permission to view this owner', status=403)
