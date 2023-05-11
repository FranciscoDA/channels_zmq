import pytest
import asyncio
import random

from channels_zmq.core import DedicatedZmqChannelLayer


@pytest.mark.asyncio
async def test_send_receive(zmq_dedicated_layer: DedicatedZmqChannelLayer, pub_resender):
    "Simple test case: can we receive a channel message that was sent by the same thread?"

    expected_message = {"type": "test.message", "text": "Ahoy-hoy!"}

    recv_task = asyncio.create_task(zmq_dedicated_layer.receive("ch1"))
    await zmq_dedicated_layer.send("ch1", expected_message)

    await pub_resender(1)

    received_message = await recv_task
    assert received_message == expected_message


@pytest.mark.asyncio
async def test_send_receive_N_channels(zmq_dedicated_layer: DedicatedZmqChannelLayer, pub_resender):
    """
    Tests whether it's possible to send a message to one of N connected channels
    without interferring with the others
    """

    # note that some of these channel names are prefixes of the others
    # we're intentionally testing that they won't collide
    channels = ["ch1", "ch11", "ch111", "ch1111"]
    random.shuffle(channels)
    expected_messages = [
        {"type": "test.message", "text": f"Message to {channel}"}
        for channel in channels
    ]

    tasks = [
        asyncio.create_task(zmq_dedicated_layer.receive(channel))
        for channel in channels
    ]

    # send in different order
    send_tuples = list(zip(channels, expected_messages))
    random.shuffle(send_tuples)
    for channel, message in send_tuples:
        await zmq_dedicated_layer.send(channel, message)

    await pub_resender(len(channels))

    for receive_task, expected_message in zip(tasks, expected_messages):
        assert await receive_task == expected_message


@pytest.mark.asyncio
async def test_group_add_receive(zmq_dedicated_layer: DedicatedZmqChannelLayer, pub_resender):
    """
    Tests whether a channel will receive group messages after being added to the group
    """
    expected_message = {"type": "test.message", "text": "Ahoy-hoy!"}

    await zmq_dedicated_layer.group_add("gr1", "ch1")

    # messages sent to gr1 should be received on ch1
    await zmq_dedicated_layer.group_send("gr1", expected_message)
    await pub_resender(1)
    received_message = await zmq_dedicated_layer.receive("ch1")
    assert received_message == expected_message

    # make sure we can still receive channel messages after adding to group
    await zmq_dedicated_layer.send("ch1", expected_message)
    await pub_resender(1)
    received_message = await zmq_dedicated_layer.receive("ch1")
    assert received_message == expected_message


@pytest.mark.asyncio
async def test_group_discard(zmq_dedicated_layer: DedicatedZmqChannelLayer, pub_resender):
    """
    Tests whether a channel will receive group messages after being added to the group
    """
    expected_message = {"type": "test.message", "text": "Ahoy-hoy!"}

    await zmq_dedicated_layer.group_add("gr1", "ch1")
    await zmq_dedicated_layer.group_discard("gr1", "ch1")

    await zmq_dedicated_layer.group_send("gr1", expected_message)
    await pub_resender(1)
    with pytest.raises(asyncio.exceptions.TimeoutError):
        received_message = await asyncio.wait_for(zmq_dedicated_layer.receive("ch1"), timeout=1.0)


def test_str_conversion(zmq_dedicated_layer: DedicatedZmqChannelLayer):
    # just for coverage purposes
    assert isinstance(str(zmq_dedicated_layer), str)


@pytest.mark.asyncio
async def test_new_channel(zmq_dedicated_layer: DedicatedZmqChannelLayer):
    # just for coverage purposes
    ch = await zmq_dedicated_layer.new_channel()
    assert isinstance(ch, str) and "!" in ch


@pytest.mark.asyncio
async def test_flush(zmq_dedicated_layer: DedicatedZmqChannelLayer, pub_resender):
    expected_message = {"type": "test.message", "text": "Ahoy-hoy!"}
    recv_task = asyncio.create_task(zmq_dedicated_layer.receive("ch1"))
    await zmq_dedicated_layer.send("ch1", expected_message)
    assert len(zmq_dedicated_layer.zmq_sub_sockets) == 1
    await pub_resender(1)
    await recv_task

    await zmq_dedicated_layer.flush()
    assert zmq_dedicated_layer.zmq_sub_sockets == {}
