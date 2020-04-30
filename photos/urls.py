from django.urls import path

from photos.views import (
    view_sensitive_image, photo_demo, sign_s3_sensitive, sign_s3_public)


urlpatterns = [
    path(
        'view_image/<file_name>', view_sensitive_image,
        name='view_sensitive_image'),  # Backwards compatible
    path(
        'view_sensitive_image/<file_name>', view_sensitive_image,
        name='view_sensitive_image'),

    path('photo_demo/', photo_demo, name='photo_demo'),
    path('sign_s3_sensitive/', sign_s3_sensitive, name='sign_s3_sensitive'),
    path('sign_s3_public/', sign_s3_public, name='sign_s3_public'),
    # Backwards compatibility. Remove a day after it's deployed.
    path('verify_id/sign_s3', sign_s3_sensitive)]
