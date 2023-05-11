import asyncio
import pytest

from channels_zmq.core import DedicatedZmqChannelLayer, EmbeddedZmqChannelLayer
import zmq.asyncio


def generate_ipc_socket_name(test_name):
    """
    Generates a socket name based on the caller function's name.
    This allows running tests concurrently without collisions between
    ZeroMQ sockets of different tests
    """
    assert test_name.startswith("test_")
    return f"ipc://ipc/{test_name}.ipc"


@pytest.fixture
def zmq_embedded_layer(request, monkeypatch):
    layer = EmbeddedZmqChannelLayer(
        generate_ipc_socket_name(request.node.originalname),
    )

    # This fixture adds a wait in the embedded layer after binding the PUB socket
    # and before sending the message.
    # This allows clients some time to connect and subscribe to the message topic.
    # Otherwise, they would miss the message and it would be dropped.
    old_init_pub_socket = layer._init_pub_socket
    async def new_init_pub_socket(*args, **kwargs):
        await old_init_pub_socket(*args, **kwargs)
        await asyncio.sleep(0.3)
    monkeypatch.setattr(layer, layer._init_pub_socket.__name__, new_init_pub_socket)

    yield layer
    asyncio.run(layer.flush())


@pytest.fixture
def zmq_dedicated_layer(request, monkeypatch):
    layer = DedicatedZmqChannelLayer(
        generate_ipc_socket_name(request.node.originalname + "-pull"),
        generate_ipc_socket_name(request.node.originalname + "-pub"),
    )

    # This fixture adds a wait in the dedicated layer after connecting the PUSH socket
    # and before sending the message.
    # This allows the resender some time to bind the sockets.
    # Otherwise, they would miss the message and it would be dropped.
    old_init_push_socket = layer._init_push_socket
    async def new_init_push_socket(*args, **kwargs):
        await old_init_push_socket(*args, **kwargs)
        await asyncio.sleep(0.3)
    monkeypatch.setattr(layer, layer._init_push_socket.__name__, new_init_push_socket)


    yield layer
    asyncio.run(layer.flush())


@pytest.fixture
def pub_resender(request):
    zmq_context = zmq.asyncio.Context.instance()
    zmq_pull_socket = zmq_context.socket(zmq.PULL)
    zmq_pub_socket = zmq_context.socket(zmq.PUB)

    zmq_pull_socket.bind(generate_ipc_socket_name(request.node.originalname + "-pull"))
    zmq_pub_socket.bind(generate_ipc_socket_name(request.node.originalname + "-pub"))

    async def resend(n):
        for i in range(n):
            msg = await zmq_pull_socket.recv()
            await zmq_pub_socket.send(msg)

    return resend
