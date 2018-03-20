""" Put random checks in here that should pass before the app deploys. """

import re

pipfile = open('Pipfile').read()

if re.compile(r'\nDjango\s*=').search(pipfile):
  raise Exception(
      'In Pipfile, change Django=... to django=... The stage environment of '
      'Heroku chokes on the upper case during automatic deployment for some '
      'reason.')

if re.compile(r'\nselenium\s*=').search(pipfile):
  raise Exception(
      'You can\'t have selenium in Pipfile. The stage environment of '
      'Heroku chokes on it during automatic deployment.')
