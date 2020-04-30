# set -e causes the script to return with a failure when any command
# fails with an error. That's important so Heroku's continuous integration
# setup catches the failure. At first I had this in apps.json
#  "environments": {
#    "test": {
#      "env": {
#        "IN_HEROKU": "yep."
#      },
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

: "${IN_HEROKU_CI?Only run test.sh in Heroku\'s CI test environment. \
stayd/heroku_ci_test_settings.py explains why.}"

# You can make sure code you're working on doesn't get submitted by accident
# by putting the literal string DO NOT SUBMIT anywhere.
echo "Testing for DO NOT SUBMIT."
echo "If this fails with 'No such file' or something, thats what it is."
# -r recursive, -I ignore binary files, -i ignore case, -n show the line
# number. I found the directory names by just runnin ls -a -l in this here
# script one time. bash is a mystery to me. This was the only way I figured out
# how to fail when grep found a thing.
$(! grep -r -I -i -n --exclude-dir=migrations --exclude-dir=.heroku --exclude-dir=.sprettur --exclude-dir=.profile.d --exclude=test.sh --exclude=README.md 'DO NOT SUBMIT\|import pdb')
echo "./lint.sh"
./lint.sh
echo "python submit_checks.py"
python submit_checks.py
echo "python manage.py migrate"
python manage.py migrate
echo "python manage.py collectstatic"
python manage.py collectstatic
echo "python clock.py --no-run"
python clock.py --no-run
echo "python manage.py test --settings=stayd.heroku_ci_test_settings"
python manage.py test --settings=stayd.heroku_ci_test_settings
