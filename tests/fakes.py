import logging

import fakeredis

from atomicpuppy.atomicpuppy import RedisCounter


class FakeRedisCounter(RedisCounter):
    def __init__(self, instance, redis=None):
        self._redis = redis or fakeredis.FakeStrictRedis()
        self._instance_name = instance
        self._logger = logging.getLogger(__name__)
