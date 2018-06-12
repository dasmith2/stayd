from django.urls import path, re_path

from reports.views import rent_revenue, reservation_search, reservation_history

urlpatterns = [
    re_path(r'rent_revenue/?$', rent_revenue, name='rent_revenue'),
    path(
        'rent_revenue/<from_date_str>/<to_date_str>',
        rent_revenue, name='rent_revenue'),

    path('reservation', reservation_search, name='reservation_search'),
    path(
        'reservation/<int:pk>', reservation_history,
        name='reservation_history')]
