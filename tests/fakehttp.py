from aiohttp.client import ClientResponse
from aiohttp.helpers import TimerNoop
from collections import deque, defaultdict
from unittest.mock import Mock
import asyncio
import functools
import http
import logging

import yarl


class FakeHttp:

    def __init__(self, loop):
        self._loop = loop
        self._callbacks = defaultdict(deque)
        self._error_on_exhausted = False

    def registerJsonUris(self, registrations):
        for uri, fn in registrations.items():
            self.registerJsonUri(uri, fn)

    def _make_response(self, uri, filename=None, status=200):
        def cb():

            def read():
                fut = asyncio.Future(loop=self._loop)
                with open(filename) as f:
                    fut.set_result(f.read().encode('utf-8'))
                return fut

            resp = ClientResponse(
                'GET',
                yarl.URL(uri),
                writer=Mock(),
                timer=TimerNoop(),
                continue100=None,
                request_info=Mock(),
                traces=[],
                loop=self._loop,
                session=Mock()
            )
            resp._headers = {
                'Content-Type': 'application/json'
            }

            resp.status = status
            resp.content = Mock()
            resp.content.read.side_effect = read
            resp.close = Mock()
            fut = asyncio.Future(loop=self._loop)
            fut.set_result(resp)
            return fut
        return cb

    def register404(self, uri):
        self.registerEmptyUri(uri, 404)

    def registerJsonUri(self, uri, filename):
        self._callbacks[uri].append(self._make_response(uri, filename))

    def registerJsonsUri(self, uri, filenames):
        for f in filenames:
            self._callbacks[uri].append(self._make_response(uri, f))

    def registerEmptyUri(self, uri, status):
        def cb():
            fut = asyncio.Future(loop=self._loop)
            resp = ClientResponse(
                'GET',
                yarl.URL('foo'),
                writer=Mock(),
                timer=TimerNoop(),
                continue100=None,
                request_info=Mock(),
                traces=[],
                loop=self._loop,
                session=Mock()
                )
            resp.status = status

            # setting this as aiohttp 3.5.4 is now checking if this value is not None
            # see aiohttp/client_reqrep.py:934
            resp.reason = http.client.responses[status]

            fut.set_result(resp)
            return fut
        self._callbacks[uri].append(cb)

    def registerCallbackUri(self, uri, cb):
        self._callbacks[uri].append(cb)

    def registerCallbacksUri(self, uri, funcs):
        for cb in funcs:
            self._callbacks[uri].append(cb)

    def registerNoMoreRequests(self, uri):
        assert not self._error_on_exhausted, (
            "registerNoMoreRequests may not be used in a test together "
            "with registerErrorWhenRegisteredRequestsExhausted")
        def fail():
            raise Exception('No more expected requests are queued')
        self._callbacks[uri].append(fail)

    def registerErrorWhenRegisteredRequestsExhausted(self):
        """Raise an exception on .respond when no responses are registered.

        This errors for *any* URI, if all registered responses have already
        been used up by other .respond()s.  This is different to
        .registerNoMoreRequests: that method only errors if one particular URI
        is .respond()ed to.

        This method may not be used in a test together with
        registerErrorWhenRegisteredRequestsExhausted.
        """
        self._error_on_exhausted = True

    def _noMoreRegisteredRequests(self):
        def accumulate(acc, deque_):
            return acc + list(deque_)
        deques = dict(self._callbacks).values()
        reduced = functools.reduce(accumulate, deques, [])
        return len(reduced) == 0

    async def respond(self, uri):
        if self._callbacks[uri]:
            cb = self._callbacks[uri].popleft()
            return await cb()
        elif self._error_on_exhausted and self._noMoreRegisteredRequests():
            raise Exception("No more expected requests are queued for any URI")
        print("No response registered for uri "+uri)

    def getMock(self):
        return Mock(side_effect=lambda m, u, **kwargs: self.respond(u))


class SpyLog(logging.StreamHandler):

    def __init__(self):
        self._logs = []
        self.setLevel(logging.DEBUG)
        self.filters = []
        self.lock = None
        self.formatter = logging.Formatter()

    def emit(self, record):
        self.formatter.format(record)
        self._logs.append(record)

    def capture(self):
        return SpyLogContextManager(self)

    @property
    def errors(self):
        return [r for r in self._logs if r.levelname == "ERROR"]

    @property
    def warnings(self):
        return [r for r in self._logs if r.levelname == "WARNING"]


class SpyLogContextManager:

    def __init__(self, log):
        self._log = log

    def __enter__(self):
        logging.getLogger().addHandler(self._log)

    def __exit__(self, type, value, traceback):
        logging.getLogger().removeHandler(self._log)
        print("logs:")
        for r in self._log._logs:
            print(r.msg)
