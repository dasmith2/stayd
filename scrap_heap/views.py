from django.contrib.staticfiles.views import serve
from django.shortcuts import render


def apply_template(request, template_name):
  return render(request, 'apply_html/{}'.format(template_name))


def apply_script(request, script_path):
  return serve(request, 'apply_scrap/scripts/{}'.format(script_path))


def apply_lib(request, file_path):
  return serve(request, 'apply_scrap/libs/{}'.format(file_path))


def apply_asset(request, file_path):
  return serve(request, 'apply_scrap/assets/{}'.format(file_path))


def apply_html_script(request, script_name):
  return serve(request, 'apply_scrap/scripts/{}'.format(script_name))
