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
from django.contrib.auth import views as auth_views
from django.urls import include, path


from guest_messages.views import edit_guest_message_templates
from guesty.views import guesty_webhook
from reports.urls import urlpatterns as report_urls
from rentals.views import ListAirvatarsAPI, RetrieveAirvatarAPI
from reservations.views import cleaning_schedule
from util.views import trigger_error, email_admins, homepage

urlpatterns = [
    path('api/', include([
        path(r'login/', include('rest_framework.urls')),
        path(
            r'airvatars/<name_slug>/', RetrieveAirvatarAPI.as_view(),
            name='retrieve-airvatar-api'),
        path(
            r'airvatars/', ListAirvatarsAPI.as_view(),
            name='list-airvatars-api')
    ])),
    path('reports/', include(report_urls)),
    path('trigger_error', trigger_error),
    path('email_admins', email_admins),
    path('guesty_webhook/<event_name>', guesty_webhook, name='guesty_webhook'),
    path(
        'admin/guest_messages/template/',
        edit_guest_message_templates, name='edit_guest_message_templates'),
    path('cleaning_schedule', cleaning_schedule, name='cleaning_schedule'),
    path('cleaning_schedule/', cleaning_schedule, name='cleaning_schedule'),
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.login, name='login'),
    path('', homepage),
]

if settings.DEBUG:
  import debug_toolbar
  urlpatterns = [
      path(r'__debug__/', include(debug_toolbar.urls))] + urlpatterns
