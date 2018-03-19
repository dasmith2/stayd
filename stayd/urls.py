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
from listings.views import ListingsAPI
from reservations.views import ReservationsAPI
from pays.views import PaypalPayinsAPI

urlpatterns = [
    path('api/', include([
        path(r'login/', include('rest_framework.urls')),
        path(r'listings/', ListingsAPI.as_view(), name='listings-api'),
        path(
            r'reservations/', ReservationsAPI.as_view(),
            name='reservations-api'),
        path(
            r'paypal_payins/', PaypalPayinsAPI.as_view(),
            name='paypal-payins-api')
    ])),
    path('admin/', admin.site.urls),
]
