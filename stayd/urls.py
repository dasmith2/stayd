"""stayd URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from listings.views import (
    CreateListingsAPI, ListAirvatarsAPI, RetrieveAirvatarAPI)
from reservations.views import CreateReservationsAPI
from pays.views import CreatePaypalPayinsAPI

urlpatterns = [
    path('api/', include([
        path(r'login/', include('rest_framework.urls')),
        path(
            r'listings/', CreateListingsAPI.as_view(),
            name='create-listings-api'),
        path(
            r'airvatars/<name_slug>/', RetrieveAirvatarAPI.as_view(),
            name='retrieve-airvatar-api'),
        path(
            r'airvatars/', ListAirvatarsAPI.as_view(),
            name='list-airvatars-api'),
        path(
            r'reservations/', CreateReservationsAPI.as_view(),
            name='create-reservations-api'),
        path(
            r'paypal_payins/', CreatePaypalPayinsAPI.as_view(),
            name='create-paypal-payins-api')
    ])),
    path('admin/', admin.site.urls),
]
