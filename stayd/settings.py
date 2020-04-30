import os
import re
import sys
import warnings

import django_heroku


# You can put your local development environment settings such as DATABASES in
# stayd/local_settings.py, which is also in .gitignore so you can modify local
# settings without affecting tracked code.
DEBUG = os.path.exists('stayd/local_settings.py')
LOCAL = DEBUG
STAGE = os.environ.get('STAGE', default='False') == 'True'
PROD = os.environ.get('PROD', default='False') == 'True'
TEST = 'test' in sys.argv
RUNSERVER = 'runserver' in sys.argv
MANAGE_COMMAND_FINDER = re.compile(r'[^\w]*manage.py')
MANAGE_COMMAND = any([MANAGE_COMMAND_FINDER.match(arg) for arg in sys.argv])
SHELL = MANAGE_COMMAND and 'shell' in sys.argv
# This is a little ugly. There are two cases where you'd be in a background
# thread. One is you're a task that was picked up by worker.py, the background
# thread worker as defined in Procfile. The other is you're a custom management
# command. Hopefully, runserver is the only non-custom mangement command that
# cares about this setting. This is less of an issue now that we use clock.py
# but we still have a few management commands available.
BACKGROUND = 'worker.py' in sys.argv or (MANAGE_COMMAND and not RUNSERVER)
IS_CLOCK = 'clock.py' in sys.argv
# This one is useful for developing css for phones and such.
PRETEND_MOBILE = False

"""
All code ought to make sense in the shell, in tests, and in production.
log_error is a bit of a special case. By default in tests and the shell it
shouldn't send emails. But one time, sending emails was precisely the thing
that was broken and I couldn't experiment in the shell. Now you can do this
in the shell:

from django.conf import settings
settings.ALWAYS_ALLOW_SEND_MAIL = True
log_error('hello', 'world') # Will actually email
"""
ALWAYS_ALLOW_SEND_MAIL = False

ALERT_OVERDUE_MESSAGES = ['guests@hihoward.com']
ALERT_HIGH_RISK_RESERVATION = ['guests@hihoward.com']
ALERT_OVERLAPPING_RESERVATIONS = ['jerseycity@hihoward.com']
ALERT_BAD_PHONE = ['jerseycity@hihoward.com']
ALERT_ESCALATED_SUBMISSION = ['jerseycity@hihoward.com']
ALERT_NEW_ID_SUBMISSION = [
    'test@stayd.com' if DEBUG else 'guests@hihoward.com']
DEFAULT_BUILDING_ALERT_EMAIL = 'jerseycity@hihoward.com'
ALERT_LIKELY_PAYIN_NOT_IDEAL = 'jerseycity@hihoward.com'
ALERT_ACCOUNTANT_ISSUES = ['seb@hihoward.com']
ALERT_NEW_BENTO_CARD_OR_TAG = 'jerseycity@hihoward.com'
ALERT_FRONT_PAYMENT_REQUIRED = 'jerseycity@hihoward.com'
ALERT_SERVICE_PROVIDER_NEEDS_PAYPAL = 'onboarding@hihoward.com'
ALERT_CANT_FIGURE_OUT_RECEIPT = 'tom@hihoward.com'
ALERT_NEW_RECEIPT = 'tom@hihoward.com'
ALERT_NEW_CLEAN_CO_WORKER = 'onboarding@hihoward.com'
ALERT_THEY_COLLECT_PAYMENT_CHANNEL = ['seb@hihoward.com', 'greg@hihoward.com']
ALERT_NETSUITE_CONFIGURATION_REQUIRED = ['greg@hihoward.com']
EMAIL_TWICE_DAILY_SLA_LESS_TICKET_COUNT = 'tom@hihoward.com'
ALERT_BACKGROUND_CHECK_BREACH = ['dave@hihoward.com', 'tom@hihoward.com']
ALERT_MUST_CANCEL = ['tasks@stayd.com']
ALERT_BGCHECK_REQUIRED = ['tasks@stayd.com']
ALERT_NPS_DETRACTOR = [
    'marc@hihoward.com', 'maria@hihoward.com', 'tom@hihoward.com']
ALERT_CLEANING_CONFIGURATION_ISSUES = ['tasks@stayd.com']

# Otherwise, when Django sends emails to the admins due to 500 errors, they're
# from root@localhost and no self respecting smtp provider lets that through.
SERVER_EMAIL = 'keys@hihowardstaffmail.com'


# So, we want to avoid any environment BUT prod from messing with external
# APIS. The last thing we want is, say, tests creating eroneous cleanings by
# accident. But just in case you actually do need to use APIs and such locally.
ALLOW_NETWORK_OVERRIDE = False

NETWORK_READS_OK = SHELL or BACKGROUND
NETWORK_WRITES_OK = PROD and NETWORK_READS_OK

MAX_ALLOWED_REQUEST_TIME = 0.5  # seconds


ALLOW_SMS_CATCH_UP_HOURS = 6

THIS_SERVERS_BASE_URL_SET = bool(os.environ.get(
    'THIS_SERVERS_BASE_URL', default=False))
THIS_SERVERS_BASE_URL = os.environ.get(
    'THIS_SERVERS_BASE_URL',
    default=(
        'Please set the THIS_SERVERS_BASE_URL environment variable with '
        'no trailing /'))
VERIFY_ID_SERVER = 'https://verifyid.hihoward.com'
KEYS_SERVER = 'https://keys.hihoward.com'
STAGE_SERVER = 'https://stage.stayd.com'
CLEAN_CO_SERVER = 'https://clean.hihoward.com'

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
MESSAGING_GOES_LIVE = os.environ.get(
    'MESSAGING_GOES_LIVE', default='2018-05-07T12:00:00')
DEFAULT_FRONT_SMS_CHANNEL_ID = 'cha_4t4h'

EMAIL_GOES_LIVE = os.environ.get(
    'EMAIL_GOES_LIVE', default='2018-10-01T00:00:00')
TEST_RENTAL = int(os.environ.get('TEST_RENTAL', 0))

PROPERLY_GOES_LIVE = os.environ.get(
    'PROPERLY_GOES_LIVE', default='2018-11-20T00:00:00')

MINIMUM_SECURITY_DEPOSIT = 100

# Build paths inside the project like this: os.path.join(settings.BASE_DIR,...)
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
    'aaircall',
    'bgcheck',
    'commands',
    'dashboard',
    'errors',
    'expenses',
    'front',
    'guest_messages',
    'guests',
    'guesty',
    'id_verify',
    'netsuite',
    'nps',
    'paypal',
    'performance',
    'photos',
    'rentals',
    'reports',
    'reservations',
    'scrap_heap',
    'stats',
    'stripe',
    'typeform',
    'util',
    'va',
    'walls',
    'work']

if DEBUG:
  # I try to keep things out of pipenv that aren't necessary in the server
  # enviroment because Heroku likes to choke unexpectedly and with unhelpful
  # messages depending on requirements. Locally you'll want to do something
  # like pip install django-debug-toolbar
  INSTALLED_APPS.append('debug_toolbar')

MIDDLEWARE = [
    'performance.middleware.TrackRequestTimeMiddleware',
    'performance.middleware.LogExceptionsMiddleware',
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
# https://developer.paypal.com/developer/accountStatus -> My Apps & Credentials
# -> REST API apps -> Create App (pick a name, submit) -> Live (in the upper
# right hand corner) -> Client ID and Secret. By the way you may have to turn
# on payouts.
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

GOOGLE_ACCOUNT_JSON = os.path.join(BASE_DIR, 'google_key.json')

# Internationalization
# https://docs.djangoproject.com/en/2.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'America/New_York'

USE_I18N = True

USE_L10N = True

USE_TZ = True

DEFAULT_CURRENCY = 'USD'

# Logging. Not a lot going on here.
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
EMAIL_ERRORS_TO = os.environ.get(
    'EMAIL_STACK_TRACES_TO', default='dave@hihoward.com')
if EMAIL_ERRORS_TO:
  ADMINS.append(
      ('Heroku errors', EMAIL_ERRORS_TO))


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
MANDRILL_API_KEY = os.environ.get('MANDRILL_API_KEY', default='')
GUEST_EMAILS_FROM = 'guests@hihowardmail.com'
GUEST_EMAILS_FROM_NAME = 'Howard Guest Services'
GUEST_EMAILS_REPLY_TO = 'guests@hihoward.com'
# What literal template name from Mailchimp should we use to inform guests that
# we will cancel their reservation due to the results of the background check
# process?
TEMPLATE_WE_MUST_CANCEL_DUE_TO_BGCHECK = 'Background check fail'

GUESTY_KEY = os.environ.get('GUESTY_KEY', default='')
GUESTY_SECRET = os.environ.get('GUESTY_SECRET', default='')

# When it comes to sensitive images, I created 2 separate AWS accounts,
# aws@stayd.com and awsdev@stayd.com. The login information for each AWS
# account is in Keeper, and should be considered sensitive because these
# accounts have credit cards attached to them and these accounts have root
# access and the ability to add aditional services, which could get awfully
# expensive in the hands of a malicious actor. Each AWS account has an IAM user
# with API keys. These default keys here are for the IAm user in
# awsdev@stayd.com's AWS account. The reason for using an IAM user is, if these
# credentials are stolen, all the hacker can really do is mess with the
# relevant s3 instances. The keys to the IAm user associated with aws@stayd.com
# who has access to the bucket containing credit card photos and such, those
# keys are in heroku settings.
S3_ACCESS_KEY_ID_SENSITIVE = os.environ.get(
    'S3_ACCESS_KEY_ID_SENSITIVE', default='AKIAWKTSKAPCTDSBI57Z')
S3_SECRET_ACCESS_KEY_SENSITIVE = os.environ.get(
    'S3_SECRET_ACCESS_KEY_SENSITIVE',
    default='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')
S3_BUCKET_NAME_SENSITIVE = os.environ.get(
    'S3_BUCKET_NAME_SENSITIVE', 'dev-stayd-id-verification')

# These keys are for an iam user named hihowardiam who has permission to both
# the dev and prod PUBLIC buckets. hihowardiam is managed by a root user whose
# login is stored in keeper as publics3@hihoward.com So if these here keys get
# stolen, all the malicious actor has is the iam user hihowardiam, and all they
# could do is mess with our public photos in dev and in prod. Not the end of
# the world.
S3_ACCESS_KEY_ID_PUBLIC = os.environ.get(
    'S3_ACCESS_KEY_ID_PUBLIC', default='AKIA24V4YCOJM3BIIQEZ')
S3_SECRET_ACCESS_KEY_PUBLIC = os.environ.get(
    'S3_SECRET_ACCESS_KEY_PUBLIC',
    default='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')
S3_BUCKET_NAME_PUBLIC = os.environ.get(
    'S3_BUCKET_NAME_PUBLIC', 'dev-hihoward-public')
PUBLIC_IMAGE_HOST = 'https://{}.s3.amazonaws.com/'.format(
    S3_BUCKET_NAME_PUBLIC)

# https://developer.typeform.com/
TYPEFORM_CLIENT_ID = os.environ.get(
    'TYPEFORM_CLIENT_ID', 'HfFQbjWgo7GwQd214WVE9GncFWcEZdCfhhYBitGzgLpX')
TYPEFORM_SECRET = os.environ.get('TYPEFORM_SECRET', '')

# https://stripe.com/docs/api
STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY', '')

# The defaults here are for the Properly sandbox environment.
PROPERLY_API_ROOT = os.environ.get(
    'PROPERLY_API_ROOT',
    'https://2g12g0e0v0.execute-api.us-east-1.amazonaws.com/sandbox')
PROPERLY_API_KEY = os.environ.get(
    'PROPERLY_API_KEY', '8N9OQ93KPX9kFpaH7g3224ppHHkSeeIs85LkJX4r')
PROPERLY_TARGET_ACCOUNT_ID = os.environ.get(
    'PROPERLY_TARGET_ACCOUNT_ID', '5ba34160038ee834c1a1b651')

# https://developer.aircall.io/api-references/
AIRCALL_API_ID = os.environ.get('AIRCALL_API_ID', '')
AIRCALL_API_TOKEN = os.environ.get('AIRCALL_API_TOKEN', '')

# https://www.twilio.com/docs/usage/api and
# https://www.twilio.com/docs/lookup/api The defaults are TEST Credentials
TWILIO_ACCOUNT_SID = os.environ.get(
    'TWILIO_ACCOUNT_SID', 'ACcf91cf10fc8b72828a4e3c3f613f63f4')
TWILIO_AUTH_TOKEN = os.environ.get(
    'TWILIO_AUTH_TOKEN', '5f524668648f94b9f85b312960e1161b')

# https://docs.authenticating.com/
AUTHENTICATING_COMPANY_ADMIN_KEY = os.environ.get(
    'AUTHENTICATING_COMPANY_ADMIN_KEY', None)
AUTHENTICATING_API_ROOT = 'https://api-v3.authenticating.com'

# Local environment overrides. I stopped using django-environ because, well, it
# just didn't seem very clear to me for starters. But then it wasn't reflecting
# os.environ in Heroku's CI environment which is, like, you had one job.
try:
  from stayd.local_settings import *  # noqa: F401,F403
except ModuleNotFoundError:
  pass

django_heroku.settings(locals())
