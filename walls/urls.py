from django.urls import path


from walls.views import walls


urlpatterns = [
    path('walls/', walls, name='walls')]
