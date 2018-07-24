from django.urls import path

from guest_messages.views import (
    edit_guest_message_templates, tracking_pixel)


urlpatterns = [
    path(
        'admin/guest_messages/template/',
        edit_guest_message_templates, name='edit_guest_message_templates'),
    path(
        '<tracking_pixel_id>/tracking_pixel.png',
        tracking_pixel, name='tracking_pixel')]
