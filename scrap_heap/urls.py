from django.conf.urls import url
from django.urls import path

from scrap_heap.views import *


urlpatterns = [
    path('apply/<template_name>', apply_template, name='apply_template'),
    path(
        'apply/html/scripts/<script_name>', apply_html_script,
        name='apply_html_script'),
    url('apply/scripts/(.+)', apply_script, name='apply_script'),
    url('libs/(.+)', apply_lib, name='apply_lib'),
    url('assets/(.+)', apply_asset, name='apply_asset')]
