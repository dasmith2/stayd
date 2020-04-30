"""
The background thread might be held up with a long running task! Check
https://keys.hihoward.com/admin/commands/commandrun/

You can see the production logs of this worker thusly:
heroku logs -t -p worker -a stayd-prod

You can see how much memory the redis queue is using by going here and clicking
on Redis To Go
https://dashboard.heroku.com/apps/stayd-prod

You can restart the worker (not the same as restarting the queue!) with
heroku ps:restart worker -a stayd-prod

Errors are automatically caught and mailed to us as long as the
util/background.py @background decorator is the mechanism used to pass tasks
to the worker.

Communicating to this worker requires a redis queue with limited memory. A
catastrophic failure we had one time was, I was passing bulky data to a
@background function. This filled up the queue, which froze, and then the
background worker became unreachable until I restarted the redis queue.

See util/background.py for many more comments, such as how to restart the
queue.
"""
import os

import django
from django.conf import settings
import redis
from rq import Worker, Queue, Connection


# This file is imported by both workers and web. Settings are already
# configured on web but not on workers.
if not settings.configured:
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stayd.settings')
  django.setup()

listen = ['high', 'default', 'low']

redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')

conn = redis.from_url(redis_url)

if __name__ == '__main__':
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work()
