from django.urls import path

from stripe.views import charge_to_reservation, resolve_unlinked_charge

urlpatterns = [
    path(
        'charge_to_reservation/', charge_to_reservation,
        name='charge_to_reservation'),
    path(
        'charge_to_reservation/<from_date_str>/<to_date_str>/',
        charge_to_reservation, name='charge_to_reservation'),
    path(
        'resolve_unlinked_charge/<charge_id>/',
        resolve_unlinked_charge, name='resolve_unlinked_charge')]
