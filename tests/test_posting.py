import json
import os
import httpretty

from uuid import uuid4

from atomicpuppy import Event, EventPublisher

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
