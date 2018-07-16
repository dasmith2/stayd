import os

from django.conf import settings
import redis
from rq import Worker, Queue, Connection

from stayd import settings as stayd_settings

settings.configure(default_settings=stayd_settings, DEBUG=False)

listen = ['high', 'default', 'low']

redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')

conn = redis.from_url(redis_url)

if __name__ == '__main__':
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work()
