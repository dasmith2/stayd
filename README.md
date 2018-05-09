# Stayd

Welcome to Stayd!

## Running Locally

To get tests running locally, your test database user needs permission to create
and destroy databases.

$ sudo su - postgres
$ psql
$ ALTER USER stayduser CREATEDB;

## Deploying

We're running on Heroku because that's just way less work for us.

## Setting up in the first place.

Let's say you wanted to tear everything down and start all over again.

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

Addons! We need logging.

heroku addons:create papertrail:choklad
  Created papertrail-octagonal-93207 as PAPERTRAIL_API_TOKEN on stayd-stage

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

## cron scheduling
We're justing using the built in Heroku scheduler which is good enough
for our purposes. To see it, run

heroku addons:open scheduler -a stayd-prod
