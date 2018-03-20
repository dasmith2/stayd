# This causes the script to return with a failure when any command
# fails with an error, which is what we want.
set -e

./lint.sh
python submit_checks.py
python manage.py test --settings=stayd.heroku_ci_test_settings
