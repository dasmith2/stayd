# Stayd

Welcome to Stayd!

## Running Locally

You'll need the code.
Install git.
Add your key to the github settings.
cd ~
git clone git@github.com:dasmith2/stayd.git

You'll need posgresql.

    sudo apt-get update
    sudo apt-get install postgresql postgresql-contrib
    # The -W here forces a prompt for a password.
    sudo -u postgres createuser --interactive -W
    Enter name of role to add: dave2
    Shall the new role be a superuser? (y/n) y
    Password: asdf1234
    sudo -u postgres psql
    create database staydweb

Uh, using -W to force a password prompt either didn't work or I made
a typo. Anyway you can also do it thusly:

    sudo -u postgres psql
    \password dave2

Now go put this in stayd/local_settings.py

    DATABASES = {
      'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'staydweb',
        'USER': 'dave2',
        'PASSWORD': 'asdf1234'
        'HOST': 'localhost',
        'PORT': '',
      }
    }

You'll need Python 3.6. If you're on Ubuntu 16.04...

    sudo add-apt-repository ppa:deadsnakes/ppa
    sudo apt-get update
    sudo apt-get install python3.6

You'll need pipenv.

    sudo apt-get install python-pip
    pip install pipenv
    cd ~/stayd
    pipenv --python /usr/bin/python3.6
    pipenv install
    pipenv shell # You run this one every time.

Or you can put some shortcuts in your ~/.bashrc or whatever. I got

    alias cd_stayd='cd /home/dave/stayd'
    alias stayd='cd_stayd; pipenv shell'
    alias gitt='eval "$(ssh-agent -s)"; ssh-add ~/.ssh/id_rsa'
    alias staydd='gitt; stayd'
    alias cd_django='cd ~/.local/share/virtualenvs/stayd-_rx4iQka/lib/python3.6/site-packages/django'

You'll need some extra packages installed that shouldn't get checked into
the pipfile, so use pip to install these.

    pip install django-debug-toolbar
    sudo snap install heroku --classic

Now you can do all kinds of rad things, such as

    ./manage.py migrate
    ./manage.py test
    ./manage.py runserver

Here's what you gotta do to run the system test.

pip install selenium
Go get the latest geckodriver here:
https://github.com/mozilla/geckodriver/releases
Extract it, and get it in your path. I just did something like
sudo mv /home/dave/Downloads/geckodriver /usr/bin

## Deploying

We're running on Heroku because that's just way less work for us.

## cron scheduling
We're justing using the built in Heroku scheduler which is good enough
for our purposes. To see it, run

heroku addons:open scheduler -a stayd-prod

## Setting up in the first place.

Let's say you wanted to tear EVERYTHING down and start all over again,
not just in your local environent, but everywhere.

DO NOT RUN THESE COMMANDS EVER!

heroku pipelines:destroy stayd-web
heroku apps:destroy stayd-stage
heroku apps:destroy stayd-prod

heroku apps:create stayd-stage --remote stayd-stage --org stayd-developers
heroku apps:create stayd-prod --remote stayd-prod --org stayd-developers

git push stayd-stage master
heroku run python manage.py migrate --app stayd-stage
heroku run python manage.py createsuperuser --app stayd-stage
heroku open --app stayd-stage

git push stayd-prod master
heroku run python manage.py migrate --app stayd-prod

Now go to Heroku and set up the Pipeline.
- Create the pipeline. Name it stayd-web.
- Go to the pipeline settings and set the owner to stayd-developers
- Add the apps to the pipeline.
- In the pipeline settings turn on CI.
- In the stayd-stage deploy settings turn on auto deploy and check
  'Wait for CI to pass before deploy'

Now set up background threads. Here's how to do it on stage.
heroku addons:create redistogo:nano -a stayd-stage

## Retiring an entire app

The trick is that migrations from other apps might reference your app
which prevents you from removing the entire folder. I follow the directions on
https://simpleisbetterthancomplex.com/tutorial/2016/07/26/how-to-reset-migrations.html
in order to reset all the migrations for an app, freeing you up to remove
the unused app entirely.

1. python manage.py makemigrations, commit, deploy, python manage.py migrate
on all databases. Make sure everything is up to date everywhere.
2. This helps you keep track of the migration situation.
python manage.py showmigrations
3. Locally,
python manage.py migrate --fake my_app zero
That will undo the migrations in my_app, but ALSO the migrations that depend
on those migrations! So do showmigrations to make sure you understand what's
up. If it removed any migrations from other apps, zero those apps out too.
python manage.py migrate --fake my_dependent_app zero
4. Locally, remove the files for the migrations that got "undone".
5. Now it's time to remove that app you don't want.
5. python manage.py makemigrations
6. Locally, pretend you installed those new initial migrations you made.
python manage.py migrate --fake-initial
7. Run the tests.
8. DO NOT GIT COMMIT AND DEPLOY YET!
8. On all other databases such as stage and production,
heroku run bash -a stayd-stage
python manage.py migrate --fake my_app zero
python manage.py migrate --fake my_dependent_app zero
9. NOW git commit and deploy.
10. On all other databases,
python manage.py migrate --fake-initial

## Developing migrations
First, I check out master and ./manage.py migrate to make sure my current local
database is up to date. Let's say that database is called stayddev. Then I make
a copy in case I screw up stayddev testing my migration.

$ sudo su - postgres
$ psql
$ CREATE DATABASE stayddev_2;
$ GRANT ALL ON DATABASE stayddev_2 TO stayduser;
$ \q
$ pg_dump stayddev | psql stayddev_2

Then,

$ git checkout -b my_new_branch
$ < write my new code >
$ ./manage.py createmigrations
$ < double check those migrations >
$ ./manage.py migrate

If everything went well, gravy. If not, and stayddev is now a hopeless
confusion, wipe it out and restore so I can try again.

$ sudo su - postgres
$ psql
$ \connect stayddev
$ DROP SCHEMA public CASCADE;
$ CREATE SCHEMA public;
$ GRANT ALL ON SCHEMA public TO postgres;
$ GRANT ALL ON SCHEMA public TO public;
$ \q
$ pg_dump stayddev_2 | stayddev

$ DO I ALSO HAVE TO...
$ COMMENT ON SCHEMA public IS 'standard public schema';
