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
