from django.urls import path

from guesty.views import turn_on_all_messages, guesty_webhook


urlpatterns = [
    path('guesty_webhook/<event_name>', guesty_webhook, name='guesty_webhook'),
    path(
        'turn_on_all_messages/',
        turn_on_all_messages,
        name='turn_on_all_messages')]
