from django.contrib.auth.models import User
from django.http import HttpResponse

from rentals.models import Building, Rental
from util.permission import user_can_groups, ACCOUNTANT
from util.views import message


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
    if user_can_groups(viewing_user, ACCOUNTANT):
      return
    if building_id and not Building.objects.filter(pk=building_id).exists():
      text = (
          'There isn\'t a building with this building_id. Perhaps it was '
          'deleted?')
      return message('Building not found', text, 404)
    if rental_id and not Rental.objects.filter(pk=rental_id).exists():
      return message(
          'Rental not found',
          'There isn\'t a rental with this rental_id. Perhaps it was deleted?',
          404)
    if owner_id and not User.objects.filter(pk=owner_id).exists():
      return message(
          'Owner not found',
          'There isn\'t an owner with this owner_id. Perhaps it was deleted?',
          404)
    if viewing_user.is_superuser:
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
