import aiohttp
import asyncio
import logging
import os
from unittest.mock import patch
from uuid import UUID, uuid4

from atomicpuppy.atomicpuppy import (
    StreamReader, SubscriptionInfoStore, SubscriptionConfig
)
from atomicpuppy import AtomicPuppy, StreamNotFoundError, HttpClientError
from tests.fakehttp import FakeHttp, SpyLog
from tests.fakes import FakeRedisCounter

from aiohttp.client import _RequestContextManager
from aiohttp import BasicAuth
from concurrent.futures import TimeoutError

SCRIPT_PATH = os.path.dirname(__file__)


class FakeRequestContext(_RequestContextManager):

    def __init__(self, coro):
        self.coro = coro

    async def __aenter__(self):
         self._resp = await self.coro
         self._resp.raise_for_status()
         return self._resp


class FakeClientSession:

    def __init__(self, fake_http, username=None, password=None):
        self.http = fake_http
        self.closed = False
        if username != None and password != None:
            self.auth = username + password
        else:
            self.auth = None

    def get(self, uri, **kwargs):

        resp = self.http.respond(uri, self.auth)

        return FakeRequestContext(resp)

    def close(self):
        self.closed = True

    async def __aenter__(self, *args):
        return self

    async def __aexit__(self, *args):
        self.close()


class AtomicPuppyContext:

    def given_fake_http_and_an_event_loop(self):
        self.loop = asyncio.new_event_loop()
        # restore global event loop unset by line above, I think?
        asyncio.set_event_loop(None)
        self.http = FakeHttp(self.loop)

    def make_and_start_atomic_puppy(
            self,
            username=None,
            password=None,
            stream_to_look_in='otherstream',
            expect_exceptions=()):

        def handler(msg):
            self.events.append(msg)

        config = {
            'streams': [stream_to_look_in],
            'host': self._host,
            'port': self._port,
            'instance': 'eventstore_reader',
            'page_size': 2
        }

        self.events = []

        with patch('aiohttp.ClientSession') as mock:
            mock.return_value = FakeClientSession(self.http, username=username, password=password)
            ap = AtomicPuppy({'atomicpuppy': config}, handler, self.loop, username, password)
            self._log = SpyLog()
            with(self._log.capture()):
                try:
                    self.loop.run_until_complete(asyncio.wait_for(ap.start(), 2))
                except expect_exceptions as exc:
                    raise exc
                    self.exc = exc
            assert mock.return_value.closed


class When_we_start_atomic_puppy_with_invalid_credentials(
        AtomicPuppyContext):

    _host = 'eventstore.local'
    _port = 2113

    def given_two_events_on_the_stream(self):
        head_uri = (
            'http://eventstore.local:2113/streams/otherstream')
        stream = SCRIPT_PATH + '/responses/full-page.json'
        self.http.registerServerCredentials('user', 'password')
        self.http.registerJsonUri(head_uri, stream)
        self.http.registerErrorWhenRegisteredRequestsExhausted()

    def because_we_start_atomic_puppy(self):
        self.make_and_start_atomic_puppy(username='wronguser', password='wrongpassword')

    def it_should_fetch_the_first_matching_event(self):
        assert isinstance(self.exc, HttpClientError)


