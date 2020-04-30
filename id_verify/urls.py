from django.urls import path

from id_verify.views import (
    verify_id, verify_id_submit, thanks_for_verifying_id,
    confirm_bgcheck_opt_out)


urlpatterns = [
    path('', verify_id, name='verify_id'),
    path('submit', verify_id_submit, name='verify_id_submit'),
    path('thanks', thanks_for_verifying_id, name='thanks_for_verifying_id'),
    path(
        'confirm_opt_out/', confirm_bgcheck_opt_out,
        name='confirm_bgcheck_opt_out')]
