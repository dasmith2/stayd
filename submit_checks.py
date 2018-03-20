""" Put random checks in here that should pass before the app deploys. """

import re
import sys


pipfile = open('Pipfile').read()

ABNORMAL = 1

if re.compile(r'\nDjango\s*=').search(pipfile):
  print(
      'In Pipfile, change Django=... to django=... and run pipenv install to '
      'update the lock file. The stage environment of Heroku chokes on the '
      'upper case Django during automatic deployment for some reason.')
  sys.exit(ABNORMAL)

if re.compile(r'\nselenium\s*=').search(pipfile):
  print(
      'You can\'t have selenium in the Pipfile. The stage environment of '
      'Heroku chokes on it during automatic deployment. Since the '
      'scrape app needs it, you\'ll have to install it manually with '
      'Pipenv install selenium, then go modify Pipfile to remove selenium, '
      'then call Pipenv install to fix the lock file.')
  sys.exit(ABNORMAL)
