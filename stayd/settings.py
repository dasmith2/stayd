import os
import re
import sys
import warnings

import django_heroku


# You can put your local development environment settings such as DATABASES in
# stayd/local_settings.py, which is also in .gitignore so you can modify local
# settings without affecting tracked code.
DEBUG = os.path.exists('stayd/local_settings.py')
TEST = 'test' in sys.argv
RUNSERVER = 'runserver' in sys.argv
MANAGE_COMMAND_FINDER = re.compile(r'[^\w]*manage.py')
MANAGE_COMMAND = any([MANAGE_COMMAND_FINDER.match(arg) for arg in sys.argv])
# This is a little ugly. There are two cases where you'd be in a background
# thread. One is you're a task that was picked up by worker.py, the background
# thread worker as defined in Procfile. The other is you're a custom
# management command. Hopefully, runserver is the only non-custom mangement
# command that cares about this setting.
BACKGROUND = 'worker.py' in sys.argv or (MANAGE_COMMAND and not RUNSERVER)


""" Guesty custom fields. The individual automation field ids are configured in
the guesty_custom_field_id of guest_messages.models.SMSTemplate and SMS.
That's why you don't see them here. """
ID_VERIFIED_FIELD_ID = '5af5fd0dc3c35f0025b2642e'
EMAIL_PROVIDED_FIELD_ID = '5af5fd0dc3c35f0025b2642d'
PHONE_PROVIDED_FIELD_ID = '5af5fd0dc3c35f0025b2642c'
ALL_AUTOMATIONS_FIELD_ID = '5afa2c379ebb42009e34f271'
PAID_IN_FULL_FIELD_ID = '5afed6c3c28d460024347bf8'
CREDIT_CARD_AUTHORIZATION_VALID_FIELD_ID = '5afed6c3c28d460024347bf7'
MARKET_RENT_FIELD_ID = '5af74a286000ec002a64a537'
COMPLETE_ID_VERIFICATION_EMAIL_FIELD_ID = '5afec8950c6ec3001f42e5b3'

ID_VERIFY_URL_AIRBNB = 'https://stayd.typeform.com/to/B3BcbH'
ID_VERIFY_URL_EVERYONE_ELSE = 'https://stayd.typeform.com/to/Y3Fpua'


ALLOW_SMS_CATCH_UP_HOURS = 6


ALERT_OVERLAPPING_MESSAGES = ['mmckay@stayd.com']
ALERT_BAD_PHONE = ['mmckay@stayd.com', 'tom@stayd.com']
ALERT_OVERPAYMENT = ['payments@stayd.com']
ALERT_NEW_ID_SUBMISSION = ['test@stayd.com' if DEBUG else 'airbnbid@stayd.com']


THIS_SERVERS_BASE_URL_SET = bool(os.environ.get(
    'THIS_SERVERS_BASE_URL', default=False))
THIS_SERVERS_BASE_URL = os.environ.get(
    'THIS_SERVERS_BASE_URL',
    default=(
        'Please set the THIS_SERVERS_BASE_URL environment variable with '
        'no trailing /'))
VERIFY_ID_SERVER = 'https://guests.stayd.com'

EXCLUDE_CLEANING_SCHEDULE_IDS = []
EXCLUDE_CLEANING_SCHEDULE_IDS_STR = os.environ.get(
    'EXCLUDE_CLEANING_SCHEDULE_IDS', default='')
if EXCLUDE_CLEANING_SCHEDULE_IDS_STR:
  EXCLUDE_CLEANING_SCHEDULE_IDS = [
      int(i) for i in EXCLUDE_CLEANING_SCHEDULE_IDS_STR.split(',')]

IN_HEROKU_CI = os.environ.get('IN_HEROKU_CI', default=False)
SECURE_SSL_REDIRECT = not IN_HEROKU_CI and not DEBUG

EXAMPLE_MOBILE_USER_AGENT = (
    'Mozilla/5.0 (Linux; Android 4.0.4; Galaxy Nexus Build/IMM76B) '
    'AppleWebKit/535.19 (KHTML, like Gecko) Chrome/18.0.1025.133 '
    'Mobile Safari/535.19')

if DEBUG:
  # This gives us stack traces for non-timezone-aware warnings.
  warnings.filterwarnings(
      'error', r"DateTimeField .* received a naive datetime",
      RuntimeWarning, r'django\.db\.models\.fields')

# This was when we started sending sms from stayd-web.
# We can remove MESSAGING_GOES_LIVE when this is empty:
# Reservation.objects.filter(
#     check_in__gt=now(),
#     reservation_created < make_aware(
#         parse_datetime(settings.MESSAGING_GOES_LIVE)))
MESSAGING_GOES_LIVE = os.environ.get(
    'MESSAGING_GOES_LIVE', default='2018-05-07T12:00:00')
FRONT_SMS_CHANNEL_ID = 'cha_4t4h'

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL = '/static/'

# Extra places for collectstatic to find static files.
STATICFILES_DIRS = (
    os.path.join(BASE_DIR, 'static'),
)


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '9j!y^@e15)tbx%i(_t$zdq-dv!#8(-@ec-ls7+5l(6oob1vvi^'

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'djmoney',
    'commands',
    'errors',
    'front',
    'guest_messages',
    'guests',
    'guesty',
    'id_verify',
    'listings',
    'pays',
    'rentals',
    'reports',
    'reservations',
    'util'
]

if DEBUG:
  # I try to keep things out of pipenv that aren't necessary in the server
  # enviroment because Heroku likes to choke unexpectedly and with unhelpful
  # messages depending on requirements. Locally you'll want to do something
  # like
  # pipenv install django-debug-toolbar # So you have the debug toolbar...
  # git checkout Pipfile Pipfile.lock # But revert these so it stays local.
  INSTALLED_APPS.append('debug_toolbar')

MIDDLEWARE = [
    # Simplified static file serving.
    # https://warehouse.python.org/project/whitenoise/
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'util.platform_detect.mobile_detection_middleware'
]

if DEBUG:
  MIDDLEWARE.append('debug_toolbar.middleware.DebugToolbarMiddleware')

ROOT_URLCONF = 'stayd.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': ['templates'],
    'APP_DIRS': True,
    'OPTIONS': {
        'debug': True,
        'string_if_invalid': 'Invalid variable: %s',
        'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages']}}]

WSGI_APPLICATION = 'stayd.wsgi.application'

INTERNAL_IPS = ['127.0.0.1']

# Literally the absolute path to the scrape directory
SCRAPE_DIR = '/home/dave/backup/source/stayd/scrape'


# DATABASES gets set on Heroku by django_heroku, so put something like this
# in your local_settings.py
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql_psycopg2',
#         'NAME': 'stayddev',
#         'USER': 'stayduser',
#         'PASSWORD': 'asdf1234',
#         'HOST': 'localhost',
#         'PORT': '',
#     }
# }


# Password validation
# https://docs.djangoproject.com/en/2.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': (
            'django.contrib.auth.password_validation.'
            'UserAttributeSimilarityValidator'),
    },
    {
        'NAME': (
            'django.contrib.auth.password_validation.MinimumLengthValidator'),
    },
    {
        'NAME': (
            'django.contrib.auth.password_validation.CommonPasswordValidator'),
    },
    {
        'NAME': (
            'django.contrib.auth.password_validation.'
            'NumericPasswordValidator'),
    },
]


# Payment stuff. WARNING: DO NOT PUT LIVE KEYS HERE! These should only be
# harmless sandbox keys. Live keys should only be set in production, and only
# using the stayd pipeline -> stayd-prod app -> Settings -> Config Variables
PAYPAL_SANDBOX_CLIENT_ID = (
    'AeOqD39LFAgOd06JwyVRq4upeEDx2sQF-hfOi8_UEf_pZYAGpwhcG6jgQ5CKk71LyQqB'
    'iOn5im1AACOf')
PAYPAL_SANDBOX_SECRET = (
    'EJ-XZfCuXZizF-nGVGN2AWVdIe0l23CHWCa71RV-pzXoUjIy8pYZVRCOdMEqbAXeflxu'
    'aWlKCOAN2oVs')
PAYPAL_SANDBOX_API_BASE_URL = 'https://api.sandbox.paypal.com/'

# Paypal requires you to submit an application to turn on Payouts in the
# Live environment. Check that here:
# https://developer.paypal.com/developer/accountStatus
PAYPAL_CLIENT_ID = os.environ.get(
    'PAYPAL_CLIENT_ID', default=PAYPAL_SANDBOX_CLIENT_ID)
PAYPAL_SECRET = os.environ.get(
    'PAYPAL_SECRET', default=PAYPAL_SANDBOX_SECRET)
PAYPAL_API_BASE_URL = os.environ.get(
    'PAYPAL_API_BASE_URL', default=PAYPAL_SANDBOX_API_BASE_URL)


# Internationalization
# https://docs.djangoproject.com/en/2.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'America/New_York'

USE_I18N = True

USE_L10N = True

USE_TZ = True

DEFAULT_CURRENCY = 'USD'

# Logging

# According to
# https://help.papertrailapp.com/kb/configuration/configuring
# -centralized-logging-from-python-apps/#logging-via-the-heroku-add-on
# This is supposed to make it so when you log in Django
# it'll show up in the logs in papertrail, which you get to by
# heroku addons:open papertrail --app=stayd-prod
# It doesn't seem to capture stack traces when the app returns a 500
# and I haven't really tested it yet though so it probably doesn't work.
LOGGING = {
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'strm': sys.stdout
        }
    }
}

# Django will automatically mail a full traceback of any error to each person
# listed in the ADMINS
ADMINS = []
# This should be set in your heroku app -> settings -> Config Variables
possible_error_email_address = os.environ.get(
    'EMAIL_STACK_TRACES_TO', default='')
if possible_error_email_address:
  ADMINS.append(
      ('Heroku errors', possible_error_email_address))

# Otherwise, when Django sends emails to the admins due to 500 errors, they're
# from root@localhost and no self respecting smtp provider lets that through.
SERVER_EMAIL = 'heroku@stayd.com'


FRONT_JSON_WEB_TOKEN = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzY29wZXMiOlsiKiJdLCJpc3MiOiJmcm9udCIsInN1YiI6InN0YXlkIn0.gg3kZep7Xgv-37DNSNBK16ulRl71FTfA9i6sEHtYzuE'  # noqa: E501

FRONT_API_SECRET = '7684cb417e25c2518e79004d650bf7b3'

# heroku addons:docs mailgun
# We're using this for server errors, alerts, that kind of thing.
MAILGUN_API_KEY = os.environ.get('MAILGUN_API_KEY', default='')
MAILGUN_DOMAIN = os.environ.get('MAILGUN_DOMAIN', default='')
MAILGUN_PUBLIC_KEY = os.environ.get('MAILGUN_PUBLIC_KEY', default='')
MAILGUN_SMTP_LOGIN = os.environ.get('MAILGUN_SMTP_LOGIN', default='')
MAILGUN_SMTP_PASSWORD = os.environ.get('MAILGUN_SMTP_PASSWORD', default='')
MAILGUN_SMTP_PORT = os.environ.get('MAILGUN_SMTP_PORT', default='')
MAILGUN_SMTP_SERVER = os.environ.get('MAILGUN_SMTP_SERVER', default='')

EMAIL_HOST = MAILGUN_SMTP_SERVER
EMAIL_PORT = MAILGUN_SMTP_PORT
EMAIL_HOST_USER = MAILGUN_SMTP_LOGIN
EMAIL_HOST_PASSWORD = MAILGUN_SMTP_PASSWORD

# We're using Mailchimp/Mandrill for emailing guests. At the moment, simply
# for transactions, not marketing.
MANDRILL_API_ROOT = 'https://mandrillapp.com/api/1.0/'
MANDRILL_API_KEY = os.environ.get('MANDRILL_API_KEY', default='')
GUEST_EMAILS_FROM = 'guests@staydmail.com'
GUEST_EMAILS_REPLY_TO = 'messages@stayd.com'

GUESTY_KEY = os.environ.get('GUESTY_KEY', default='')
GUESTY_SECRET = os.environ.get('GUESTY_SECRET', default='')

# Amazon AWS S3. The defaults are for the dev S3 bucket.
S3_ACCESS_KEY_ID = os.environ.get(
    'S3_ACCESS_KEY_ID', default='AKIAIYYRTKA6W3TKGINQ')
S3_SECRET_ACCESS_KEY = os.environ.get(
    'S3_SECRET_ACCESS_KEY', default='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')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'dev-stayd-id-verification')


# Local environment overrides. I stopped using django-environ because, well,
# it just didn't seem very clear to me for starters. But then it wasn't
# reflecting os.environ in Heroku's CI environment which is, like, you had one
# job.
try:
  from stayd.local_settings import *  # noqa: F401,F403
except ModuleNotFoundError:
  pass

django_heroku.settings(locals())
