"""
The urls you're looking for are probably in id_verify. id_verify knows about
bgcheck but not the other way around.
"""
from django.urls import path

from bgcheck.views import (
    door_person, get_bg_check_reservation_data, verify_us_id_cc,
    mark_passed, bgcheck_dashboard, bgcheck_totals, bgcheck_detail)


urlpatterns = [
    path('door_person/', door_person, name='door_person'),
    path(
        'get_bg_check_reservation_data/<channel>/',
        get_bg_check_reservation_data,
        name='get_bg_check_reservation_data'),
    path(
        'mark_passed/<bgcheck_id>/<true_or_false>/', mark_passed,
        name='mark_passed'),
    path(  # Legacy
        'mark_passed_backup/<bgcheck_id>/<true_or_false>/', mark_passed),
    path(
        'verify_us_id_cc/<channel_id>/', verify_us_id_cc,
        name='verify_us_id_cc'),

    # Secret hidden dashboard stuff
    path(
        'bgcheck_totals/', bgcheck_totals, name='bgcheck_totals'),
    path(
        'bgcheck_totals/<from_date_str>/<to_date_str>/', bgcheck_totals,
        name='bgcheck_totals'),
    path(
        'bgcheck_dashboard/', bgcheck_dashboard, name='bgcheck_dashboard'),
    path(
        'bgcheck_dashboard/<from_date_str>/<to_date_str>/', bgcheck_dashboard,
        name='bgcheck_dashboard'),
    path(
        'bgcheck_detail/<reservation_pk>/', bgcheck_detail,
        name='bgcheck_detail')]
