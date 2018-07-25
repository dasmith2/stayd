from django.urls import path

from guest_messages.views import edit_guest_message_templates


urlpatterns = [
    path(
        'admin/guest_messages/smstemplate/',
        edit_guest_message_templates, name='edit_guest_message_templates')]
