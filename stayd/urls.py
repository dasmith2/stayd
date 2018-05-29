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
from django.conf import settings
from django.contrib import admin
from django.urls import include, path


from guest_messages.views import edit_guest_message_templates
from guesty.views import guesty_webhook
from rentals.views import ListAirvatarsAPI, RetrieveAirvatarAPI
from owner_payouts.views import edit_owner_payout
from pays.views import CreatePaypalPayinsAPI
from reports.views import rent_revenue
from util.views import trigger_error, email_admins, homepage

urlpatterns = [
    path('api/', include([
        path(r'login/', include('rest_framework.urls')),
        path(
            r'airvatars/<name_slug>/', RetrieveAirvatarAPI.as_view(),
            name='retrieve-airvatar-api'),
        path(
            r'airvatars/', ListAirvatarsAPI.as_view(),
            name='list-airvatars-api'),
        path(
            r'paypal_payins/', CreatePaypalPayinsAPI.as_view(),
            name='create-paypal-payins-api')
    ])),
    path('trigger_error', trigger_error),
    path('email_admins', email_admins),
    path('guesty_webhook/<event_name>', guesty_webhook, name='guesty_webhook'),
    path('rent_revenue', rent_revenue, name='rent_revenue'),
    path(
        'rent_revenue/<from_date_str>/<to_date_str>',
        rent_revenue, name='rent_revenue'),
    path(
        'admin/owner_payouts/ownerpayout/<owner_payout_id>/change/',
        edit_owner_payout, name='edit_owner_payout'),
    path(
        'admin/guest_messages/template/',
        edit_guest_message_templates, name='edit_guest_message_templates'),
    path('admin/', admin.site.urls),
    path('', homepage),
]

if settings.DEBUG:
  import debug_toolbar
  urlpatterns = [
      path(r'__debug__/', include(debug_toolbar.urls))] + urlpatterns
