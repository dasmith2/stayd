# set -e causes the script to return with a failure when any command
# fails with an error. That's important so Heroku's continuous integration
# setup catches the failure. At first I had this in apps.json
#  "environments": {
#    "test": {
#      "scripts": {
#        "test-setup": "python manage.py migrate",
#        "test": "python submit_checks.py"
#        "test": "python manage.py test --settings=stayd.heroku_ci_test_settings"
#        "test": "./lint.sh"
#      }
#    }
#  }
# But Heroku only ran the last "test"!

set -e

./lint.sh
python submit_checks.py
python manage.py test --settings=stayd.heroku_ci_test_settings
