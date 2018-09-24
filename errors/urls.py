from django.urls import path

from errors.views import js_error


urlpatterns = [
    path('js_error', js_error, name='js_error')]
