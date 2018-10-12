from django.contrib.auth import views as auth_views
from django.urls import path

from dashboard.views import dashboard, dashboard0, DASHBOARD_LOGIN


urlpatterns = [
    path(
        DASHBOARD_LOGIN[1:],  # Remove leading slash
        auth_views.LoginView.as_view(template_name='dashboard_login.html'),
        name='dashboard_login'),
    path('dashboard0/', dashboard0, name='dashboard0'),
    path('dashboard/', dashboard, name='dashboard')]
