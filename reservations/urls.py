from django.urls import path

from reservations.views import (
    unresolved_likely_payin_not_ideal, resolved_likely_payin_not_ideal,
    resolved_likely_payin_not_ideal_csv, unresolved_likely_payin_not_ideal_csv,
    resolve_payin)


urlpatterns = [
    path(
        'unresolved_likely_payin_not_ideal/',
        unresolved_likely_payin_not_ideal,
        name='unresolved_likely_payin_not_ideal'),
    path(
        'unresolved_likely_payin_not_ideal_csv/',
        unresolved_likely_payin_not_ideal_csv,
        name='unresolved_likely_payin_not_ideal_csv'),
    path(
        'resolved_likely_payin_not_ideal/',
        resolved_likely_payin_not_ideal,
        name='resolved_likely_payin_not_ideal'),
    path(
        'resolved_likely_payin_not_ideal_csv/',
        resolved_likely_payin_not_ideal_csv,
        name='resolved_likely_payin_not_ideal_csv'),
    path('resolve_payin/<pk>/', resolve_payin, name='resolve_payin')]
