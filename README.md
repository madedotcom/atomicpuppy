[![Build Status](https://travis-ci.org/madedotcom/atomicpuppy.svg?branch=master)](https://travis-ci.org/madedotcom/atomicpuppy)
# atomicpuppy
A service-activator component for eventstore, written in Python


## A Brief and Mostly Useless Quickstart:

```yaml
# config.yaml
atomicpuppy:
    host: localhost
    port: 2113
    # each stream will be polled by a separate async http client
    streams:
        - stream_a
        - stream_b
        - stream_with_a_#date#
    # the counter keeps track of which messages have been processed
    counter:
        redis:
            host: localhost
            port: 6379
```


```python
# main.py
# AtomicPuppy uses asyncio coroutines for concurrent IO
import asyncio
import logging
import signal
from atomicpuppy import AtomicPuppy

# AtomicPuppy needs a callback to pass you messages.
def handle(msg):
  print(msg)

# Config is read from yaml files.
ap = AtomicPuppy('config.yaml', handle)
loop = asyncio.get_event_loop()

# to kill the puppy, call stop()
def stop():
    logging.debug("SIGINT received, shutting down")
    ap.stop()

loop.add_signal_handler(signal.SIGINT, stop)

# and to start it call start.
loop.run_until_complete(ap.start())
```


## Run the tests

A `tox.ini` file is provided to run the tests with different versions of Python.

To run the tests:

1. Make sure you have the Python 3.5, 3.6, 3.7 and 3.8 headers installed (for Ubuntu please refer to https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa)
2. `pip install -r test-requirements.txt` from the root folder of the repository
3. Run `tox` from the root folder of the repository


## About python version

There is a bug in asyncio for python3.4 that was fixed in other versions.
This is the bug report: https://bugs.python.org/issue23812
Because of that we have dropped support for python3.4 and we recommend to use
python3.7.
