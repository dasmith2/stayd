from django.urls import path

from rentals.views import clean_up_dupe_rentals


urlpatterns = [
    path(
        'clean_up_dupe_rentals/', clean_up_dupe_rentals,
        name='clean_up_dupe_rentals')]
