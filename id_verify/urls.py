from django.urls import path

from id_verify.views import (
    verify_id, verify_id_submit, sign_s3, thanks_for_verifying_id,
    submissions, payment_problems, no_cc_info, view_image,
    resend_id_verification, escalate_submission, escalated_submissions)


urlpatterns = [
    path('', verify_id, name='verify_id'),
    path('submit', verify_id_submit, name='verify_id_submit'),
    path('thanks', thanks_for_verifying_id, name='thanks_for_verifying_id'),
    path('sign_s3', sign_s3, name='sign_s3'),
    path('view_image/<file_name>', view_image, name='view_image'),
    path('submissions', submissions, name='submissions'),
    path(
        'escalate_submission/<submission_id>', escalate_submission,
        name='escalate_submission'),
    path(
        'escalated_submissions/<submission_id>', escalated_submissions,
        name='escalated_submissions'),
    path(
        'escalated_submissions', escalated_submissions,
        name='escalated_submissions'),
    path('payment_problems', payment_problems, name='payment_problems'),
    path('no_cc_info', no_cc_info, name='no_cc_info'),
    path(
        'resend_id_verification/<reservation_id>', resend_id_verification,
        name='resend_id_verification')
]
