from django.urls import path

from typeform.views import typeform_webhook, see_response, see_raw_event


urlpatterns = [
    path(
        'typeform/webhook/', typeform_webhook, name='typeform_webhook'),
    path(
        'admin/typeform/rawevent/<pk>/change/', see_raw_event,
        name='see_raw_event'),
    path(
        'admin/typeform/response/<pk>/change/', see_response,
        name='see_response')]
