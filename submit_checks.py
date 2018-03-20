""" Put random checks in here that should pass before the app deploys. """

import re
import sys


pipfile = open('Pipfile').read()

ABNORMAL = 1

if re.compile(r'\nDjango\s*=').search(pipfile):
  print(
      'In Pipfile, change Django=... to django=... The stage environment of '
      'Heroku chokes on the upper case during automatic deployment for some '
      'reason.')
  sys.exit(ABNORMAL)

if re.compile(r'\nselenium\s*=').search(pipfile):
  print(
      'You can\'t have selenium in Pipfile. The stage environment of '
      'Heroku chokes on it during automatic deployment.')
  sys.exit(ABNORMAL)
