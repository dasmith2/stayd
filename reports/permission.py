class Checker(object):
  def can_view_owner(self, viewing_user, owner_id):
    return not owner_id or viewing_user.pk == owner_id or viewing_user.is_staff

  def can_view_rental(self, viewing_user, rental):
    if not rental:
      return True
    return viewing_user.pk == rental.owner.pk or viewing_user.is_staff
