from django.urls import path, re_path

from reports.views import (
    rent_revenue, reservation_search, reservation_history, see_raw_event_json,
    reservation_list, time_series, csv_options, csv_download, time_series_data,
    total_data)

urlpatterns = [
    path(
        'rent_revenue/<from_date_str>/<to_date_str>',
        rent_revenue, name='rent_revenue'),
    re_path(r'rent_revenue/?$', rent_revenue, name='rent_revenue'),
    path(
        'rent_revenue/rental_<int:rental_id>/<from_date_str>/<to_date_str>',
        reservation_list, name='reservation_list'),
    path(
        'rent_revenue/time_series/<interval>/<from_date_str>/<to_date_str>',
        time_series, name='time_series'),
    re_path(r'rent_revenue/time_series/?$', time_series, name='time_series'),
    path(
        'rent_revenue/csv_options', csv_options, name='csv_options'),
    path(
        'rent_revenue/csv_download', csv_download, name='csv_download'),

    path('reservation', reservation_search, name='reservation_search'),
    path(
        'reservation/<int:pk>', reservation_history,
        name='reservation_history'),
    path('raw_event/<int:pk>', see_raw_event_json, name='see_raw_event_json'),
    path(
        'time_series_data/<interval>/<from_date_str>/<to_date_str>',
        time_series_data, name='time_series_data'),
    path(
        'total_data/<from_date_str>/<to_date_str>',
        total_data, name='total_data')]
