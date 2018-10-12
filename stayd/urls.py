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
from django.conf.urls import handler404
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path


from dashboard.urls import urlpatterns as dashboard_urls
from errors.urls import urlpatterns as error_patterns
from id_verify.urls import urlpatterns as verify_id_urls
from guest_messages.urls import urlpatterns as guest_messages_urls
from guesty.views import guesty_webhook
from properly.urls import urlpatterns as properly_urls
from reports.urls import urlpatterns as report_urls
from reservations.views import cleaning_schedule
from scrap_heap.urls import urlpatterns as scrap_heap_patterns
from stats.urls import urlpatterns as stats_urls
from util.views import trigger_error, email_admins, homepage

urlpatterns = [
    path('verify_id/', include(verify_id_urls)),
    path('reports/', include(report_urls)),
    path('stats/', include(stats_urls)),
    path('trigger_error', trigger_error),
    path('email_admins', email_admins),
    path('guesty_webhook/<event_name>', guesty_webhook, name='guesty_webhook'),
    path('properly/', include(properly_urls)),
    path('', include(guest_messages_urls)),
    path('', include(dashboard_urls)),
    path('', include(error_patterns)),
    path('cleaning_schedule', cleaning_schedule, name='cleaning_schedule'),
    path('cleaning_schedule/', cleaning_schedule, name='cleaning_schedule'),
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('', homepage),
    # When you log into the dashboard (on 127.0.0.1 anyway) with no ?next= you
    # get sent here, which 404s.
    path('accounts/profile/', homepage),
    path('scrap_heap/', include(scrap_heap_patterns))
]

handler404 = 'util.views.error_404_view'  # noqa:F811
handler500 = 'util.views.error_500_view'  # noqa:F811

if settings.DEBUG:
  import debug_toolbar
  urlpatterns = [
      path(r'__debug__/', include(debug_toolbar.urls))] + urlpatterns
