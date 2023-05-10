import asyncio
import pytest

from channels_zmq.core import EmbeddedZmqChannelLayer


def generate_ipc_socket_name(test_name):
    """
    Generates a socket name based on the caller function's name.
    This allows running tests concurrently without collisions between
    ZeroMQ sockets of different tests
    """
    assert test_name.startswith("test_")
    return f"ipc://ipc/{test_name}.ipc"

@pytest.fixture
def zmq_embedded_layer(request):
    layer = EmbeddedZmqChannelLayer(generate_ipc_socket_name(request.node.originalname))
    yield layer
    asyncio.run(layer.flush())

@pytest.fixture
def slow_bind(monkeypatch):
    old_init_pub_socket = EmbeddedZmqChannelLayer._init_pub_socket

    async def new_init_pub_socket(*args, **kwargs):
        await old_init_pub_socket(*args, **kwargs)
        # add a wait after binding the socket and before sending the message
        # this allows clients some time to connect and subscribe to the topic
        # otherwise, they would miss the message and it would be dropped
        await asyncio.sleep(0.3)

    monkeypatch.setattr(EmbeddedZmqChannelLayer, EmbeddedZmqChannelLayer._init_pub_socket.__name__, new_init_pub_socket)