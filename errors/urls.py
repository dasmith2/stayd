from django.urls import path

from errors.views import js_error, see_error


urlpatterns = [
    path('js_error', js_error, name='js_error'),
    path('admin/errors/stayderror/<pk>/change/', see_error, name='see_error')]
