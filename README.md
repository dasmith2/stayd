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
