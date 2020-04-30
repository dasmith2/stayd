from django.urls import path

from xxero.views import (
    conflicted_coconut, conflicted_coconuts, merchant_category_2_coconut)


urlpatterns = [
    path(
        'conflicted_coconuts/', conflicted_coconuts,
        name='conflicted_coconuts'),
    path(
        'conflicted_coconut/<pk>/', conflicted_coconut,
        name='conflicted_coconut'),
    path(
        'merchant_category_2_coconut/', merchant_category_2_coconut,
        name='merchant_category_2_coconut')]
