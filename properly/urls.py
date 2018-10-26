from django.urls import path

from properly.views import properly_webhook, hours_and_pay_report


urlpatterns = [
    path('webhook', properly_webhook, name='properly_webhook'),
    path(
        'hours_and_pay_report', hours_and_pay_report,
        name='hours_and_pay_report')]
