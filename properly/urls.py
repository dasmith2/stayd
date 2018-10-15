from django.urls import path

from properly.views import properly_webhook


urlpatterns = [
    path('webhook', properly_webhook, name='properly_webhook')]
