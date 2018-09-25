from django.urls import path

from stats.views import total_data, time_series_data


urlpatterns = [
    path(
        'time_series_data/<interval>/<from_date_str>/<to_date_str>',
        time_series_data, name='time_series_data'),
    path(
        'total_data/<from_date_str>/<to_date_str>',
        total_data, name='total_data')]
