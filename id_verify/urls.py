from django.urls import path

from id_verify.views import (
    verify_id, sign_s3, thanks_for_verifying_id,
    submissions, payment_problems, no_cc_info, view_image,
    resend_id_verification, background_test)


urlpatterns = [
    path('', verify_id, name='verify_id'),
    path('bg', background_test, name='background_test'),
    path('thanks', thanks_for_verifying_id, name='thanks_for_verifying_id'),
    path('sign_s3', sign_s3, name='sign_s3'),
    path('view_image/<file_name>', view_image, name='view_image'),
    path('submissions', submissions, name='submissions'),
    path('payment_problems', payment_problems, name='payment_problems'),
    path('no_cc_info', no_cc_info, name='no_cc_info'),
    path(
        'resend_id_verification/<reservation_id>', resend_id_verification,
        name='resend_id_verification')
]
