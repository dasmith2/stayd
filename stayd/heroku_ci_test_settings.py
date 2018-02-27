# DANGER DANGER DANGER: If you use these settings and run tests, they will
# totally wipe out the database. This is for continuous integration on
# Heroku only, where tests are run in an isolated environment that does not
# have permission to create and destroy databases.

# Note that the default ./manage.py test behavior creates a fresh database
# to test on.

# See https://gist.github.com/cordery/d52d9ba44541fabaf4b012f4e62d675b
# for more discussion.

from stayd.settings import *

# or whatever you use to load the Heroku database settings
DATABASES['default']['TEST'] = env.db('DATABASE_URL')

print "Can I put print statements in here?"
print "env.db has {}".format(env.db('DATABASE_URL'))

TEST_RUNNER = 'django_heroku.HerokuDiscoverRunner'
