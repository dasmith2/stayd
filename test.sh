./lint.sh
python submit_checks.py
python manage.py test --settings=stayd.heroku_ci_test_settings
