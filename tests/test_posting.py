import json
import os
import httpretty

from uuid import uuid4

from atomicpuppy import Event, EventPublisher
from atomicpuppy.errors import InvalidDataException

SCRIPT_PATH = os.path.dirname(__file__)


class When_a_message_is_posted:

    stream = str(uuid4())
    event_id = str(uuid4())
    _host = 'fakehost'
    _port = 42

    def given_a_publisher(self):
        self.publisher = EventPublisher(self._host, self._port)

    @httpretty.activate
    def because_an_event_is_published_on_a_stream(self):
        httpretty.register_uri(
            httpretty.POST,
            "http://{}:{}/streams/{}".format(self._host, self._port, self.stream),
            body='{}')

        data = {'foo': 'bar'}
        metadata = {'lorem': 'ipsum'}
        evt = Event(self.event_id, 'my-event-type', data, self.stream, None, metadata)
        self.publisher.post(evt)
        self.response_body = json.loads(httpretty.last_request().body.decode())[0]

    def it_should_be_a_POST(self):
        assert(httpretty.last_request().method == "POST")

    def it_should_have_sent_the_correct_id(self):
        assert(self.response_body["eventId"] == self.event_id)

    def it_should_have_sent_the_correct_type(self):
        assert(self.response_body["eventType"] == 'my-event-type')

    def it_should_have_sent_the_correct_body(self):
        assert(self.response_body["data"] == {"foo": "bar"})

    def it_should_have_sent_the_correct_metadata(self):
        assert(self.response_body["metadata"] == {"lorem": "ipsum"})


class When_a_message_is_posted_to_eventstore:

    stream = str(uuid4())
    event_id = str(uuid4())
    _host = 'localhost'
    _port = 2113

    def given_a_publisher(self):
        self.publisher = EventPublisher(self._host, self._port)

    @httpretty.activate
    def because_an_event_is_published_on_a_stream(self):
        httpretty.register_uri(
            httpretty.POST,
            "http://{}:{}/streams/{}".format(self._host, self._port, self.stream),
            body='{}')

        data = {'foo': 'bar'}
        metadata = {'lorem': 'ipsum'}
        evt = Event(self.event_id, 'my-event-type', data, self.stream, None, metadata)
        self.publisher.post(evt)
        self.response_body = json.loads(httpretty.last_request().body.decode())[0]

    def it_should_be_a_POST(self):
        assert(httpretty.last_request().method == "POST")

    def it_should_have_sent_the_correct_id(self):
        assert(self.response_body["eventId"] == self.event_id)

    def it_should_have_sent_the_correct_type(self):
        assert(self.response_body["eventType"] == 'my-event-type')

    def it_should_have_sent_the_correct_body(self):
        assert(self.response_body["data"] == {"foo": "bar"})

    def it_should_have_sent_the_correct_metadata(self):
        assert(self.response_body["metadata"] == {"lorem": "ipsum"})


class When_a_message_is_posted_to_eventstore_no_metadata:

    stream = str(uuid4())
    event_id = str(uuid4())
    _host = 'localhost'
    _port = 2113

    def given_a_publisher(self):
        self.publisher = EventPublisher(self._host, self._port)

    @httpretty.activate
    def because_an_event_is_published_on_a_stream(self):
        httpretty.register_uri(
            httpretty.POST,
            "http://{}:{}/streams/{}".format(self._host, self._port, self.stream),
            body='{}')

        data = {'foo': 'bar'}
        evt = Event(self.event_id, 'my-event-type', data, self.stream, None)
        self.publisher.post(evt)
        self.response_body = json.loads(httpretty.last_request().body.decode())[0]

    def it_should_be_a_POST(self):
        assert(httpretty.last_request().method == "POST")

    def it_should_have_sent_the_correct_id(self):
        assert(self.response_body["eventId"] == self.event_id)

    def it_should_have_sent_the_correct_type(self):
        assert(self.response_body["eventType"] == 'my-event-type')

    def it_should_have_sent_the_correct_body(self):
        assert(self.response_body["data"] == {"foo": "bar"})

    def it_should_have_empty_metadata(self):
        assert(self.response_body["metadata"] == {})


class When_multiple_events_are_posted_to_eventstore_in_batch:
    stream = str(uuid4())
    event1_id = str(uuid4())
    event2_id = str(uuid4())
    _host = 'localhost'
    _port = 2113

    def given_a_publisher(self):
        self.publisher = EventPublisher(self._host, self._port)

    @httpretty.activate
    def because_events_are_published_on_a_stream(self):
        httpretty.register_uri(
            httpretty.POST,
            "http://{}:{}/streams/{}".format(self._host, self._port, self.stream),
            body='{}')

        events = [
            Event(self.event1_id, 'my-event-type', {'foo': 'bar'}, self.stream, None),
            Event(self.event2_id, 'my-event-type', {'foo2': 'bar2'}, self.stream, None),
        ]
        self.publisher.post(events)
        self.response_body = json.loads(httpretty.last_request().body.decode())

    def it_should_be_a_POST(self):
        assert(httpretty.last_request().method == "POST")

    def it_should_have_sent_all_events(self):
        assert(len(self.response_body) == 2)

    def it_should_have_sent_the_correct_ids(self):
        assert(self.response_body[0]["eventId"] == self.event1_id)
        assert(self.response_body[1]["eventId"] == self.event2_id)

    def it_should_have_sent_the_correct_type(self):
        assert(self.response_body[0]["eventType"] == 'my-event-type')
        assert(self.response_body[1]["eventType"] == 'my-event-type')

    def it_should_have_sent_the_correct_body(self):
        assert(self.response_body[0]["data"] == {"foo": "bar"})
        assert(self.response_body[1]["data"] == {"foo2": "bar2"})


class When_multiple_events_for_different_streams_are_posted_to_eventstore_in_batch:
    stream1 = str(uuid4())
    stream2 = str(uuid4())
    event1_id = str(uuid4())
    event2_id = str(uuid4())
    _host = 'localhost'
    _port = 2113
    invalid_data_exception_raised = False

    def given_a_publisher(self):
        self.publisher = EventPublisher(self._host, self._port)

    @httpretty.activate
    def because_events_are_published_in_batch_on_multiple_streams(self):
        httpretty.register_uri(
            httpretty.POST,
            "http://{}:{}/streams/{}".format(self._host, self._port, self.stream1),
            body='{}')

        events = [
            Event(self.event1_id, 'my-event-type', {'foo': 'bar'}, self.stream1, None),
            Event(self.event2_id, 'my-event-type', {'foo2': 'bar2'}, self.stream2, None),
        ]
        try:
            self.publisher.post(events)
        except InvalidDataException:
            self.invalid_data_exception_raised = True
            return

        self.response_body = json.loads(httpretty.last_request().body.decode())

    def it_should_raise_the_exception(self):
        assert self.invalid_data_exception_raised
