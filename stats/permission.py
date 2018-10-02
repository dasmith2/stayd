from django.http import HttpResponse

from rentals.models import Rental


class Checker(object):
  def _can_view_owner(self, viewing_user, owner_id):
    return not owner_id or viewing_user.pk == owner_id or viewing_user.is_staff

  def _can_view_rental(self, viewing_user, rental):
    if not rental:
      return True
    return viewing_user.pk == rental.building.owner.pk or viewing_user.is_staff

  def get_permission_problems(
      self, request_user, rental_id=None, owner_id=None):
    if rental_id and not self._can_view_rental(
        request_user, Rental.objects.get(pk=rental_id)):
      return HttpResponse(
          'You don\'t have permission to view this rental', status=403)
    if not self._can_view_owner(request_user, owner_id):
      return HttpResponse(
          'You don\'t have permission to view this owner', status=403)
