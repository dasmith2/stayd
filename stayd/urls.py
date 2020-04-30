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
from django.urls import include, path
from django.views.generic.base import RedirectView

from bgcheck.urls import urlpatterns as bgcheck_urls
from dashboard.urls import urlpatterns as dashboard_urls
from errors.urls import urlpatterns as error_patterns
from guest_messages.urls import urlpatterns as guest_messages_urls
from guesty.urls import urlpatterns as guesty_urls
from id_verify.urls import urlpatterns as id_verify_urls
from netsuite.urls import urlpatterns as netsuite_patterns
from nps.urls import urlpatterns as nps_urls
from photos.urls import urlpatterns as photo_urls
from rentals.urls import urlpatterns as rentals_urls
from reports.urls import urlpatterns as report_urls
from reservations.urls import urlpatterns as reservation_patterns
from scrap_heap.urls import urlpatterns as scrap_heap_patterns
from stats.urls import urlpatterns as stats_patterns
from stripe.urls import urlpatterns as stripe_patterns
from typeform.urls import urlpatterns as typeform_patterns
from util.views import trigger_error, email_admins, homepage
from va.urls import (
    urlpatterns as va_urls, legacy_patterns as va_legacy_urls)
from walls.urls import urlpatterns as walls_patterns
from work.urls import urlpatterns as work_urls


favicon_view = RedirectView.as_view(url='/static/favicon.ico', permanent=True)

urlpatterns = [
    path('favicon.ico', favicon_view),

    path('verify_id/', include(id_verify_urls)),
    path('va/', include(va_urls)),
    path('verify_id/', include(va_legacy_urls)),

    path('', include(rentals_urls)),
    path('', include(report_urls)),
    path('stats/', include(stats_patterns)),
    path('stripe/', include(stripe_patterns)),
    path('trigger_error/', trigger_error),
    path('email_admins', email_admins),
    path('', include(guesty_urls)),
    path('', include(work_urls)),
    path('', include(guest_messages_urls)),
    path('', include(dashboard_urls)),
    path('', include(error_patterns)),
    path('', include(typeform_patterns)),
    path('', include(walls_patterns)),
    path('', include(reservation_patterns)),
    path('', include(bgcheck_urls)),
    path('', include(netsuite_patterns)),
    path('', include(nps_urls)),
    path('', include(photo_urls)),
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
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
