from django.urls import path

from id_verify.views import (
    sign_s3, thanks_for_verifying_id, view_image,
    id_verification_list, verify_id)


urlpatterns = [
    path('', verify_id, name='verify_id'),
    path('thanks', thanks_for_verifying_id, name='thanks_for_verifying_id'),
    path('sign_s3', sign_s3, name='sign_s3'),
    path('view_image/<file_name>', view_image, name='view_image'),
    path(
        'id_verification_list', id_verification_list,
        name='id_verification_list')
]
