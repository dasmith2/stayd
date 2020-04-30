from django.urls import path

from nps.views import (
    rate_us, get_test_nps_channel_id, nps_aggregate, nps_details)


urlpatterns = [
    # Gather ratings
    path('rate_us/<channel_id>/', rate_us, name='rate_us'),

    # Analyze results
    path('nps_aggregate/', nps_aggregate, name='nps_aggregate'),
    path('nps_details/', nps_details, name='nps_details'),
    path(
        'nps_details/<from_date_str>/<to_date_str>/', nps_details,
        name='nps_details'),

    # Web tests
    path(
        'get_test_nps_channel_id/', get_test_nps_channel_id,
        name='get_test_nps_channel_id')]
