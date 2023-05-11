# channels_zmq
[![Tests status](https://github.com/FranciscoDA/channels_zmq/actions/workflows/tests.yml/badge.svg)](https://github.com/FranciscoDA/channels_zmq/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/channels-zmq)](https://pypi.org/project/channels-zmq/)

A channel layer implementation using ZeroMQ PUB-SUB topology.


### Installation


Install package from PyPI:
```sh
pip install channels-zmq
```


### Usage

Configure the layer in your Django settings file. You can choose one of the two implementations described below:


##### Embedded layer

```py
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_zmq.core.EmbeddedZmqChannelLayer",
        "CONFIG": {
            "pub_socket_address": "<SOME SOCKET ADDRESS>",
            "capacity": 100,
            "expiry": 60,
        },
    },
}
```

The embedded layer binds a ZeroMQ PUB socket inside the process that calls `send` or `group_send`.
Consumers will connect their SUB sockets to the same socket.

While this is a very lightweight implementation, it only allows a single process to call `send` and `group_send` with
the same layer.

If you need to send data created through other processes, you should create a different layer or use the [dedicated layer](#dedicated-layer).
```
               +----------------+
               |PRODUCER PROCESS|
               |----------------|
               |   PUB SOCKET   |
               +----------------+
                  ^     ^    ^
                  |     |    |
      +-----------+     |    +----------+
      |                 |               |
+------------+   +------------+   +------------+
| SUB SOCKET |   | SUB SOCKET |   | SUB SOCKET |
|------------|   |------------|   |------------|
| CONSUMER 1 |   | CONSUMER 2 |   | CONSUMER 3 |
+------------+   +------------+   +------------+
```


##### Dedicated layer

```py
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_zmq.core.DedicatedZmqChannelLayer",
        "CONFIG": {
            "pull_socket_address": "<DAEMON PULL SOCKET ADDRESS>",
            "pub_socket_address": "<DAEMON PUB SOCKET ADDRESS",
            "capacity": 100,
            "expiry": 60,
        },
    },
}
```

The dedicated layer connects a ZeroMQ PUSH socket to a the configured PULL socket location when you call `send` or `group_send`.
Consumers will connect to the configured PUB socket location instead.

While this implementation allows multiple processes to send messages over the same layer, it requires you to implement
a daemon process that will read messages on the PULL socket and send them through the PUB socket.

```
                  +--------------------------+
                  |      DAEMON PROCESS      |
                  |--------------------------|
                  | PUB SOCKET | PULL SOCKET |
                  +--------------------------+
                      ^   ^           ^   ^
                      |   |           |   |
      +---------------+   |           |   +----------------+
      |                   |           |                    |
+------------+   +------------+   +-------------+   +-------------+
| SUB SOCKET |   | SUB SOCKET |   | PUSH SOCKET |   | PUSH SOCKET |
|------------|   |------------|   |-------------|   |-------------|
| CONSUMER 1 |   | CONSUMER 2 |   | PRODUCER 1  |   | PRODUCER 2  |
+------------+   +------------+   +-------------+   +-------------+
```

