"""Atomicpuppy implementation.

Don't import from this module: import from the top-level atomicpuppy package.


Event Store terminology cheat sheet:

Here's the first and last 'page':

head -> event 10000, say (first)     ...     ...
        event 9999                           event 1
                ...                            event 0 (last)

The most recent event in time is on the left.

The directions are named like this:

<-- forwards ---                       --- backwards -->

And the links on each page are named like this:

            <<first        ...         last>>
            <previous      ...          next>
"""

from collections import namedtuple, defaultdict
from enum import Enum
from importlib import import_module
from uuid import UUID
import aiohttp
import asyncio
import datetime
import json
import logging
import platform
import random

from retrying import retry
import pybreaker
import redis
import requests
import yaml

from atomicpuppy.errors import (
    HttpClientError,
    HttpNotFoundError,
    InvalidDataException,
    RejectedMessageException,
    StreamNotFoundError,
    UrlError,
)


SubscriptionConfig = namedtuple('SubscriptionConfig', ['streams',
                                                       'counter_factory',
                                                       'instance_name',
                                                       'host',
                                                       'port',
                                                       'timeout',
                                                       'page_size'])


class Event:

    def __init__(self, id, type, data, stream, sequence, metadata=None, correlation_id=None):
        self.id = id
        self.type = type
        self.data = data
        self.stream = stream
        self.sequence = sequence
        self._location = None
        self.metadata = metadata or {}
        self.correlation_id = correlation_id

    @property
    def location(self):
        """Return a string uniquely identifying the event.

        This string can be used to find the event in the event store UI (cf. id
        attribute, which is the UUID that at time of writing doesn't let you
        easily find the event).
        """
        if self._location is None:
            self._location = "{}/{}-{}".format(
                self.stream,
                self.type,
                self.sequence,
            )
        return self._location

    def __str__(self):
        return "{}/{}-{} ({}): {} {}".format(
            self.stream,
            self.type,
            self.sequence,
            self.id,
            self.data,
            self.metadata
        )


class EventCounterCircuitBreaker(pybreaker.CircuitBreakerListener):

    def __init__(self):
        self._log = logging.getLogger(__name__)

    def before_call(self, cb, func, *args, **kwargs):
        "Called before the circuit breaker `cb` calls `func`."
        pass

    def state_change(self, cb, old_state, new_state):
        if new_state.name == 'open':
            self._log.error("Opening event counter circuit")
        elif new_state.name == 'closed':
            self._log.info("Event counter circuit closed")

    def failure(self, cb, exc):
        "Called when a function invocation raises a system error."
        pass

    def success(self, cb):
        "Called when a function invocation succeeds."
        pass


counter_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=20, reset_timeout=60, listeners=[
        EventCounterCircuitBreaker()
    ]
)


class SubscriberInfo:

    def __init__(
            self,
            stream,
            uri,
            last_read=-1):
        self._stream = stream
        self._uri = uri
        self._last_read = last_read

    @property
    def stream(self):
        return self._stream

    @property
    def last_read(self):
        return self._last_read

    @property
    def uri(self):
        return self._uri


class Page:

    def __init__(self, js, logger):
        self._js = js
        self._logger = logger

    def is_empty(self):
        # TODO: I'm not certain what types js["entries"] can have.  Find out
        # and remove any un-needed calls of this method (I'm assuming only type
        # list).
        return not self._js["entries"]

    def is_event_present(self, event_number):
        for e in self._js["entries"]:
            if e["positionEventNumber"] <= event_number:
                return True
        else:
            return False

    def iter_events_since(self, event_number):
        for e in reversed(self._js['entries']):
            if e["positionEventNumber"] > event_number:
                evt = self._make_event(e)
                if evt is not None:
                    yield evt

    def iter_events_matching(self, predicate):
        if not self.is_empty():
            for e in self._js["entries"]:
                evt = self._make_event(e)
                if evt is None:
                    continue
                if predicate(evt):
                    self._logger.info('Found first matching event: %s', evt)
                    yield evt

    def get_link(self, rel):
        for link in self._js["links"]:
            if(link["relation"] == rel):
                return link["uri"]

    def _make_event(self, e):
        try:
            data = json.loads(e["data"])
        except KeyError:
            # Eventstore allows events with no `data` to be posted. If that
            # happens, then atomicpuppy doesn't know what to do
            self._logger.warning(
                "No `data` key found on event {}".format(e))
            return None
        except ValueError:
            self._logger.error(
                "Failed to parse json data for %s message %s",
                e.get("eventType"), e.get("eventId"))
            return None
        try:
            metadata = json.loads(e["metadata"])
        except KeyError:
            metadata = {}

        type = e["eventType"]
        id = UUID(e["eventId"])
        stream = e["positionStreamId"]
        sequence = e["positionEventNumber"]

        return Event(id, type, data, stream, sequence, metadata)


class StreamReader:

    def __init__(self, queue, stream_name, loop, instance_name, subscriptions_store, session, nosleep=False):
        self._fetcher = StreamFetcher(None, loop=loop, nosleep=nosleep, session=session)
        self._queue = queue
        self._loop = loop
        self._stream = stream_name
        self._subscriptions = subscriptions_store
        self.logger = logging.getLogger('atomicpuppy.stream-reader@{}/{}'.format(instance_name, stream_name))

    async def start_consuming(self, once=False):
        self._running = True
        while self._running:
            try:
                await self.consume()
                if(once or not self._running):
                    break
                await asyncio.sleep(5)
            except UrlError as e:
                self.logger.exception(
                    "Failed to make a request with uri %s",
                    e.uri)
                self.stop()
            except HttpClientError as e:
                self.logger.exception(
                    "Received bad http response with status %d from %s",
                    e.status,
                    e.uri)
                self.stop()
            except asyncio.CancelledError:
                pass

    def stop(self):
        self._running = False
        self.logger.info("Stopping")
        self._fetcher.stop()

    async def consume(self):
        subscription = self._subscriptions.get(self._stream)
        if subscription.last_read > -1:
            self.logger.debug(
                "Last read event is %d - seeking last read on page %s",
                subscription.last_read,
                subscription.uri)
            await self.seek_on_page(subscription.uri)
        else:
            page = await self._fetcher.fetch(subscription.uri)
            last = page.get_link("last")
            if last:
                self.logger.debug(
                    "No last read event, skipping to last page %s",
                    last)
                await self._walk_forwards(last)
            else:
                self.logger.debug(
                    "No last read event, yielding events from this page %s",
                    subscription.uri)
                await self._raise_page_events(page)

    async def seek_on_page(self, uri):
        self.logger.debug("Looking for last read event on page %s", uri)
        page = await self._fetcher.fetch(uri)
        return await self._seek_to_last_read(page)

    async def _walk_forwards(self, prev_uri):
        uri = prev_uri
        while True:
            self.logger.debug("walking forwards from %s", uri)
            page = await self._fetcher.fetch(uri)
            if not page.is_empty():
                self.logger.debug("raising events from page %s", uri)
                await self._raise_page_events(page)
            prev_uri = page.get_link("previous")
            if not prev_uri:
                # loop until there's a prev link, otherwise it means
                # we are at the end or we are fetching an empty page
                self.logger.debug(
                    "walk to head completed, new polling uri is %s",
                    uri)
                self._subscriptions.update_uri(self._stream, uri)
                break

            self.logger.debug("Continuing to previous page %s", prev_uri)
            uri = prev_uri


    async def _raise_page_events(self, page):
        subscription = self._subscriptions.get(self._stream)
        last_read = subscription.last_read
        self.logger.debug("Raising events on %s since %s", self._stream, last_read)
        for evt in page.iter_events_since(last_read):
            self.logger.debug("Raising %s", evt)
            await self._queue.put(evt)
            self._subscriptions.update_sequence(self._stream, evt.sequence)

    async def _seek_to_last_read(self, page):
        subscription = self._subscriptions.get(self._stream)
        if page.is_event_present(subscription.last_read):
            self.logger.debug(
                "Found last read event on current page, raising events")
            await self._raise_page_events(page)
            prev = page.get_link("previous")
            if prev:
                await self._walk_forwards(prev)
                return
            else:
                self.logger.debug("No previous link")

        # TODO: when we're on HEAD and have processed all events this starts
        # seeking back towards last (the oldest event).  This is unintentional
        # and we should stop doing it.  Conceivably this might be hiding other
        # bugs so needs a bit of care to fix...
        nxt = page.get_link("next")
        if nxt:
            self.logger.debug('Seeking back to %s', nxt)
            await self.seek_on_page(nxt)


class EventFinder:

    def __init__(self, fetcher, stream_name, loop, instance_name, head_uri):
        self._fetcher = fetcher
        self._loop = loop
        self._stream = stream_name
        self._head_uri = head_uri
        self._logger = logging.getLogger('atomicpuppy.finder@{}/{}'.format(instance_name, stream_name))

    async def find_backwards(self, stream_name, predicate, predicate_label='predicate'):
        """Return first event matching predicate, or None if none exists.

        Note: 'backwards', both here and in Event Store, means 'towards the
        event emitted furthest in the past'.
        """
        logger = self._logger.getChild(predicate_label)
        logger.info('Fetching first matching event')
        uri = self._head_uri
        try:
            page = await self._fetcher.fetch(uri)
        except HttpNotFoundError as e:
            raise StreamNotFoundError() from e
        while True:
            evt = next(page.iter_events_matching(predicate), None)
            if evt is not None:
                return evt

            uri = page.get_link("next")
            if uri is None:
                logger.warning("No matching event found")
                return None

            page = await self._fetcher.fetch(uri)


class state(Enum):
    green = 0
    amber = 1
    red = 2


class StreamFetcher:

    def __init__(self, policy, loop, session, nosleep=False):
        self._policy = policy
        self._loop = loop
        self._log = logging.getLogger(__name__)
        self._state = state.green
        self._running = True
        self._sleep = None
        self._nosleep = nosleep
        self._exns = set()
        self.session = session

    def stop(self):
        self._running = False
        if(self._sleep):
            self._sleep.cancel()

    def sleeps(self, uri):
        max_time = 60
        attempts = 0
        last_time = 0
        self._state = state.amber
        while(True):
            if(last_time < max_time):
                attempts = attempts + 1
            elif self._state == state.amber:
                self._state = state.red
                self._log.error(
                    "Stream fetcher has failed to connect to eventstore at %s in the last %d attempts",
                    uri,
                    attempts)
            last_time = (2**attempts)
            jitter = random.uniform(-0.5, 0.5)
            yield (last_time) + jitter

    def log(self, e, uri):
        if(type(e) not in self._exns):
            self._log.warn(
                "Error occurred while requesting %s",
                uri,
                exc_info=True)
            self._exns.add(type(e))

    def set_result(self, fut, result):
        """Helper setting the result only if the future was not cancelled."""
        if fut.cancelled():
            return
        fut.set_result(result)

    async def sleep(self, delay):
        if self._nosleep:
            return
        self._sleep = asyncio.futures.Future(loop=self._loop)

        self._sleep._loop.call_later(
            delay,
            self.set_result,
            self._sleep, None)

        self._log.debug("retrying fetch in %d seconds", delay)
        return await self._sleep

    async def fetch(self, uri):
        sleep_times = self.sleeps(uri)
        self._exns = set()
        self._state = state.green
        for s in sleep_times:
            headers = {"Accept": "application/json"}
            params = {"embed": "body"}
            try:
                async with self.session.get(uri, params=params, headers=headers) as response:
                    # 200 OK? Return the Page
                    if(response.status == 200):
                        self._log.debug("Fetched %s", uri)
                        js = await response.json()
                        return Page(js, self._log)
            # Wonky URI? Raise to caller
            except ValueError as e:
                raise UrlError(e)
            # Error from the HTTP response?
            except aiohttp.ClientResponseError as e:
                self.log(e, uri)
                # For a 404, raise HttpNotFound
                if e.code == 404:
                    raise HttpNotFoundError(uri, 404)
                # For a client error other than a timeout, raise HttpClientError
                # Timeouts should log and sleep
                if e.code < 500 and e.code != 408:
                    raise HttpClientError(uri, e.code)
            # Other connection errors and malformed payloads just log and sleep
            except (aiohttp.ClientError) as e:
                self.log(e, uri)
            # Http timeout? Log and sleep
            except asyncio.TimeoutError as e:
                self.log(e, uri)

            await self.sleep(s)


def _ensure_coroutine_function(func):
    """Return a coroutine function.

    func: either a coroutine function or a regular function

    Note a coroutine function is not a coroutine!
    """
    if asyncio.iscoroutinefunction(func):
        return func
    else:
        async def coroutine_function(evt):
            return func(evt)

        return coroutine_function


class EventRaiser:

    def __init__(self, queue, counter, callback, loop=None):
        self._queue = queue
        self._callback = callback
        self._counter = counter
        self._loop = loop or asyncio.get_event_loop()
        self._logger = logging.getLogger(__name__)

    def stop(self):
        self._is_running = False
        self._logger.info("Stopping")

    async def start(self):
        self._is_running = True
        while self._loop.is_running() and self._is_running:
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1)
                if not msg:
                    continue
                coro = _ensure_coroutine_function(self._callback)
                await coro(msg)
                try:
                    self._counter[msg.stream] = msg.sequence
                except pybreaker.CircuitBreakerError:
                    pass
                except:
                    self._logger.exception("Failed to persist last read event with {}".format(type(self._counter)))
            except RejectedMessageException:
                self._logger.warn("%s message %s was rejected and has not been processed",
                                  msg.type, msg.id)
            except asyncio.TimeoutError:
                pass
            except:
                self._logger.exception("Failed to process message %s", msg)

    async def consume_events(self):
        self._is_running = True
        while self._loop.is_running() and self._is_running:
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1)
                if not msg:
                    self._is_running = False
                    return
                await _ensure_coroutine_function(self._callback)(msg)
                try:
                    self._counter[msg.stream] = msg.sequence
                except pybreaker.CircuitBreakerError:
                    pass
                except redis.RedisError:
                    self._logger.warn("Failed to persist last read event")
            except RejectedMessageException:
                self._logger.warn("%s message %s was rejected and has not been processed",
                                  msg.type, msg.id)
            except asyncio.TimeoutError:
                self._is_running = False
            except:
                self._logger.exception("Failed to process message %s", msg)
                self._is_running = False


class EventCounter:

    def __setitem__(self, stream, event):
        raise NotImplementedError("setitem")

    def __getitem__(self, stream):
        raise NotImplementedError("getitem")


class RedisCounter(EventCounter):

    def __init__(self, host, port, instance):
        self._redis = redis.StrictRedis(
            host=host,
            port=port,
        )
        self._instance_name = instance
        self._logger = logging.getLogger(__name__)

    @retry(wait_exponential_multiplier=1000, wait_exponential_max=10000, stop_max_delay=60000)
    def __getitem__(self, stream):
        self._logger.debug("Fetching last read event for stream "+stream)
        key = self._key(stream)
        val = self._redis.get(key)
        if(val):
            val = int(val)
            self._logger.info(
                "Last read event for stream %s is %d",
                stream,
                val)
            return val
        return -1

    @counter_circuit_breaker
    def __setitem__(self, stream, val):
        self._logger.debug("Setting redis pointer for %s to %s", stream, val)
        key = self._key(stream)
        self._redis.set(key, val)

    def _key(self, stream):
        return "urn:atomicpuppy:"+self._instance_name+":"+stream+":position"


class StreamConfigReader:

    _logger = logging.getLogger(__name__)

    def read(self, config_file):
        cfg = None
        if isinstance(config_file, dict):
            cfg = config_file.get('atomicpuppy')
        elif isinstance(config_file, str):
            with open(config_file) as file:
                cfg = yaml.load(file, yaml.SafeLoader).get('atomicpuppy')
        else:
            cfg = yaml.load(config_file, yaml.SafeLoader).get('atomicpuppy')


        streams = []
        instance = cfg.get('instance') or platform.node()
        for stream in cfg.get("streams"):
            streams.append(stream)
        ctr = self._make_counter(cfg, instance)
        return SubscriptionConfig(streams=streams,
                                  counter_factory=ctr,
                                  instance_name=instance,
                                  host=cfg.get("host") or 'localhost',
                                  port=cfg.get("port") or 2113,
                                  timeout=cfg.get("timeout") or 20,
                                  page_size=cfg.get("page_size") or 20)

    def _make_counter(self, cfg, instance):
        counter_config = cfg.get("counter")
        if not counter_config:
            return lambda: defaultdict(lambda: -1)
        if counter_config:
            _class = counter_config.get("class")
            package = counter_config.get("package")
            parameters = counter_config.get("parameters")
            try:
                Module = getattr(import_module(package), _class)
                return lambda: Module(instance=instance, **parameters)
            except Exception as ex:
                self._logger.exception("Unexpected error when creating a counter:")
                raise CounterConfigurationError(counter_config)


class CounterConfigurationError(Exception):

    def __init__(self, config):
        super().__init__("The following configuration is invalid: {}".format(config))


class SubscriptionInfoStore:

    """
    This class acts like an in-memory buffer of subscriptions.
    It keeps track of subscriptions based on the stream_name
    with dynamic parts replaced.

    It's needed so that new SubscriberInfo objects can be created
    before a consumption when dynamic streams produce a new stream
    name.
    """

    def __init__(self, config, counter):
        self.subscriptions = {}
        self.config = config
        self.counter = counter
        self._logger = logging.getLogger("SubscriptionInfoStore")

    def get(self, stream_name):
        parsed_name = self._parse(stream_name)
        if parsed_name not in self.subscriptions.keys():
            last_read_for_stream = self.counter[parsed_name]
            self._logger.info("Creating new SubscriberInfo for {} from event number {}".format(parsed_name, last_read_for_stream))
            s = SubscriberInfo(parsed_name, uri=self._build_uri(parsed_name, last_read_for_stream), last_read=last_read_for_stream)
            self.subscriptions[parsed_name] = s

        return self.subscriptions[parsed_name]

    def update_sequence(self, stream_name, sequence):
        # the input stream_name can be the unparsed name
        s = self.get(stream_name)
        new_subscription = SubscriberInfo(
            stream=s._stream,
            uri=s.uri,
            last_read=sequence)
        old_subscription = self.subscriptions[s._stream]
        assert(old_subscription.last_read < sequence)
        self.subscriptions[s._stream] = new_subscription

    def update_uri(self, stream_name, uri):
        # the input stream_name can be the unparsed name
        s = self.get(stream_name)
        new_subscription = SubscriberInfo(
            stream=s._stream,
            uri=uri,
            last_read=s.last_read)
        self.subscriptions[s._stream] = new_subscription

    def _build_uri(self, stream_name, last_read_for_stream=-1):
        if last_read_for_stream < 0:
            last_read_for_stream = 0

        return 'http://{}:{}/streams/{}/{}/forward/{}'.format(
            self.config.host,
            self.config.port,
            stream_name,
            last_read_for_stream,
            self.config.page_size)

    def _parse(self, stream_name):
        if '#date#' not in stream_name:
            return stream_name

        today = datetime.date.today().isoformat()
        return stream_name.replace("#date#", today)


class EventStoreJsonEncoder(json.JSONEncoder):

    def default(self, o):
        try:
            if(isinstance(o, UUID)):
                return str(o)
            return json.JSONEncoder.default(self, o)
        except Exception:
            logging.error(type(o))


class EventPublisher:

    def __init__(self, host, port):
        self._es_url = '{}:{}'.format(host, port)
        self._logger = logging.getLogger("EventPublisher")

    @retry(wait_exponential_multiplier=1000, wait_exponential_max=10000, stop_max_delay=30000,
           retry_on_result=lambda r: r.status_code >= 500)
    def post(self, event, correlation_id=None):
        if correlation_id:
            event.correlation_id = correlation_id
        return self.batch_create([event])

    @retry(wait_exponential_multiplier=1000, wait_exponential_max=10000, stop_max_delay=30000,
           retry_on_result=lambda r: r.status_code >= 500)
    def post_multiple(self, events):
        return self.batch_create(events)

    def batch_create(self, events):
        if not all(events[0].stream == event.stream for event in events):
            raise InvalidDataException("All events in the POST have to be for the same stream")

        events_count = len(events)

        uri = 'http://{}/streams/{}'.format(self._es_url, events[0].stream)
        headers = {'Content-Type': 'application/vnd.eventstore.events+json'}
        extra = {'stream': events[0].stream}
        extra.update(headers)
        extra.update({
            'es_uri': uri,
            'method': 'POST',
            'events_count': events_count,
        })
        self._logger.info(
            "Posting {} event(s) to {}. Headers: {}".format(
                events_count, uri, headers,
            ),
            extra=extra,
        )

        data = []
        for event in events:
            if event.correlation_id:
                event.data["correlation_id"] = event.correlation_id
            data.append(
                {
                    "eventId": event.id,
                    "eventType": event.type,
                    "data": event.data,
                    "metadata": event.metadata,
                },
            )

        r = requests.post(
            uri,
            headers=headers,
            data=EventStoreJsonEncoder().encode(data),
            timeout=0.5,
        )

        self._logger.debug(
            "Posting events {} to {}. Headers: {}".format([e.__dict__ for e in events], uri, headers),
            extra=extra,
        )

        if r.status_code:
            extra.update({
                'status_code': r.status_code
            })
            self._logger.info(
                "Received status code {status_code} from EventStore POST.".format(**extra),
                extra=extra,
            )

        return r
