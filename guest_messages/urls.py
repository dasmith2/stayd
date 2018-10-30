from django.urls import path

from guest_messages.views import (
    edit_sms_templates, edit_email_templates, send_test_email, send_test_sms,
    mandrill_webhook, unsubscribe, message_delays)


urlpatterns = [
    path(
        'admin/guest_messages/smstemplate/',
        edit_sms_templates, name='edit_sms_templates'),
    path('send_test_sms', send_test_sms, name='send_test_sms'),
    path(
        'admin/guest_messages/emailtemplate/',
        edit_email_templates, name='edit_email_templates'),
    path('send_test_email', send_test_email, name='send_test_email'),
    path('mandrill_webhook', mandrill_webhook, name='mandrill_webhook'),
    path('message_delays', message_delays, name='message_delays'),
    path(
        'message_delays/<from_date_str>/<to_date_str>', message_delays,
        name='message_delays'),
    path('unsub', unsubscribe, name='unsubscribe')]
