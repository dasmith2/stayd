from django.urls import path

from airbnb.views import upload_airbnb_csv, see_airbnb_csv_upload


urlpatterns = [
    path('upload_airbnb_csv/', upload_airbnb_csv, name='upload_airbnb_csv'),
    path(
        'see_upload/<pk>/', see_airbnb_csv_upload,
        name='see_airbnb_csv_upload')]
