from django.urls import path

from va.views import (
    submissions, cc_action_required, no_cc_info,
    resend_id_verification, escalate_submission,
    escalated_submissions, get_reservation_for_high_risk_web_test,
    get_reservation_for_id_verify_test, must_cancel,
    bgcheck, high_risk_approval, over_charges, reservations, va_reservation,
    inquiry_risk_score_calculator)


urlpatterns = [
    path('submissions/', submissions, name='submissions'),
    path(
        'escalate_submission/<submission_id>/', escalate_submission,
        name='escalate_submission'),
    path(
        'escalated_submissions/<submission_id>/', escalated_submissions,
        name='escalated_submissions'),
    path('must_cancel/', must_cancel, name='must_cancel'),
    path('bgcheck/', bgcheck, name='bgcheck'),
    path('high_risk_approval/', high_risk_approval, name='high_risk_approval'),
    path('over_charges/', over_charges, name='over_charges'),
    path(
        'escalated_submissions/', escalated_submissions,
        name='escalated_submissions'),
    path('cc_action_required/', cc_action_required, name='cc_action_required'),
    path('no_cc_info/', no_cc_info, name='no_cc_info'),
    path(
        'resend_id_verification/<reservation_id>/', resend_id_verification,
        name='resend_id_verification'),
    path(
        'get_reservation_for_id_verify_test/<channel>/',
        get_reservation_for_id_verify_test,
        name='get_reservation_for_id_verify_test'),
    path(
        'get_reservation_for_high_risk_web_test/',
        get_reservation_for_high_risk_web_test,
        name='get_reservation_for_high_risk_web_test'),
    path('reservations/', reservations, name='va_reservations'),
    path('reservation/<pk>/', va_reservation, name='va_reservation'),
    path(
        'inquiry_risk_score_calculator/', inquiry_risk_score_calculator,
        name='inquiry_risk_score_calculator')]


legacy_patterns = [
    path('submissions', submissions),
    path('escalate_submission/<submission_id>', escalate_submission),
    path('escalated_submissions/<submission_id>', escalated_submissions),
    path('must_cancel/', must_cancel),
    path('bgcheck/', bgcheck),
    path('backup_bgcheck/', bgcheck),
    path('over_charges/', over_charges),
    path('escalated_submissions', escalated_submissions),
    path('cc_action_required', cc_action_required),
    path('no_cc_info', no_cc_info),
    path('resend_id_verification/<reservation_id>', resend_id_verification)]
