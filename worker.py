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
