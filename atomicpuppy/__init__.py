from .atomicpuppy import (
    Event,
    EventCounter,
    EventPublisher,
    EventRaiser,
    EventStoreJsonEncoder,
    RedisCounter,
    StreamConfigReader,
    StreamFetcher,
    StreamReader,
    SubscriptionInfoStore,
    EventFinder as EventFinder_,
)
from .errors import (
    FatalError,
    HttpClientError,
    HttpNotFoundError,
    HttpServerError,
    RejectedMessageException,
    StreamNotFoundError,
    UrlError,
)

import asyncio
import aiohttp


class EventFinder:

    def __init__(self, cfg_file, loop=None, username=None, password=None):
        """
        cfg_file: dictionary or filename or yaml text
        """
        self._config = StreamConfigReader().read(cfg_file)

        self._session_auth = None
        if username != None and password != None:
            self._session_auth = aiohttp.BasicAuth(
                    login=username,
                    password=password,
                    encoding='utf-8')

        self._loop = loop or asyncio.get_event_loop()

    async def find_backwards(self, stream, predicate, predicate_label='predicate'):
        async with aiohttp.ClientSession(
                read_timeout=self._config.timeout,
                conn_timeout=self._config.timeout,
                raise_for_status=True,
                loop=self._loop,
                auth=self._session_auth) as session:

            instance_name = (
                self._config.instance_name + ' find_backwards {}'.format(stream)
            )
            fetcher = StreamFetcher(
                None, loop=self._loop, nosleep=False, session=session)
            head_uri = 'http://{}:{}/streams/{}/head/backward/{}'.format(
                self._config.host,
                self._config.port,
                stream,
                self._config.page_size)
            finder = EventFinder_(
                fetcher=fetcher,
                stream_name=stream,
                loop=self._loop,
                instance_name=instance_name,
                head_uri=head_uri,
            )
            result = await finder.find_backwards(stream, predicate, predicate_label)
            return result


class AtomicPuppy:

    def __init__(self, cfg_file, callback, loop=None, username=None, password=None):
        """
        cfg_file: dictionary or filename or yaml text
        """
        self.config = StreamConfigReader().read(cfg_file)
        self.callback = callback
        self._loop = loop or asyncio.get_event_loop()
        self._queue = asyncio.Queue(maxsize=20, loop=self._loop)

        auth = None
        if username != None and password != None:
            auth = aiohttp.BasicAuth(login=username, password=password, encoding='utf-8')

        self.session = aiohttp.ClientSession(
                read_timeout=self.config.timeout,
                conn_timeout=self.config.timeout,
                raise_for_status=True,
                loop=self._loop,
                auth=auth)

    def start(self, run_once=False):
        c = self.counter = self.config.counter_factory()
        self._messageProcessor = EventRaiser(self._queue,
                                             c,
                                             self.callback,
                                             self._loop)
        subscription_info_store = SubscriptionInfoStore(self.config, c)
        self.readers = [
            StreamReader(
                queue=self._queue,
                stream_name=s,
                loop=self._loop,
                instance_name=self.config.instance_name,
                subscriptions_store=subscription_info_store,
                session=self.session)
            for s in self.config.streams
        ]
        self.tasks = [s.start_consuming(once=run_once) for s in self.readers]
        if run_once:
            self.tasks.append(self._messageProcessor.consume_events())
        else:
            self.tasks.append(self._messageProcessor.start())
        return asyncio.gather(*self.tasks, loop=self._loop)

    def stop(self):
        self.session.close()
        for s in self.readers:
            s.stop()
        self._messageProcessor.stop()


__all__ = [
    AtomicPuppy,
    Event,
    EventCounter,
    EventFinder,
    EventPublisher,
    EventStoreJsonEncoder,
    FatalError,
    HttpClientError,
    HttpNotFoundError,
    HttpServerError,
    RedisCounter,
    RejectedMessageException,
    StreamNotFoundError,
    UrlError,
]
