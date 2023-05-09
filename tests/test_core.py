import pytest
import asyncio
import random

@pytest.mark.asyncio
async def test_send_receive(zmq_single_publisher_layer, slow_bind):
    """
    Simple test case: can we receive a channel message that was sent by the same thread?
    """
    expected_message = {"type": "test.message", "text": "Ahoy-hoy!"}

    # Need to start the coroutine that receives the message before sending the message.
    # When executed, this task connects the client and subscribes to the topic,
    # Otherwise the message will be dropped by the PUB socket as soon as it detects
    # that there are no clients connected
    recv_task = asyncio.create_task(zmq_single_publisher_layer.receive("ch1"))
    await zmq_single_publisher_layer.send("ch1", expected_message)
    received_message = await recv_task

    assert received_message == expected_message


@pytest.mark.asyncio
async def test_send_receive_N_channels(zmq_single_publisher_layer, slow_bind):
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
        asyncio.create_task(zmq_single_publisher_layer.receive(channel))
        for channel in channels
    ]

    # send in different order
    send_tuples = list(zip(channels, expected_messages))
    random.shuffle(send_tuples)
    for channel, message in send_tuples:
        await zmq_single_publisher_layer.send(channel, message)

    for receive_task, expected_message in zip(tasks, expected_messages):
        assert await receive_task == expected_message

@pytest.mark.asyncio
async def test_group_add_receive(zmq_single_publisher_layer, slow_bind):
    """
    Tests whether a channel will receive group messages after being added to the group
    """
    expected_message = {"type": "test.message", "text": "Ahoy-hoy!"}

    await zmq_single_publisher_layer.group_add("gr1", "ch1")
    await zmq_single_publisher_layer.group_send("gr1", expected_message)
    received_message = await zmq_single_publisher_layer.receive("ch1")
    assert received_message == expected_message

    # make sure we can still receive channel messages after adding to group
    await zmq_single_publisher_layer.send("ch1", expected_message)
    received_message = await zmq_single_publisher_layer.receive("ch1")
    assert received_message == expected_message


@pytest.mark.asyncio
async def test_group_discard(zmq_single_publisher_layer, slow_bind):
    """
    Tests whether a channel will receive group messages after being added to the group
    """
    expected_message = {"type": "test.message", "text": "Ahoy-hoy!"}

    await zmq_single_publisher_layer.group_add("gr1", "ch1")
    await zmq_single_publisher_layer.group_discard("gr1", "ch1")

    await zmq_single_publisher_layer.group_send("gr1", expected_message)
    with pytest.raises(asyncio.exceptions.TimeoutError):
        received_message = await asyncio.wait_for(zmq_single_publisher_layer.receive("ch1"), timeout=3.0)


def test_str_conversion(zmq_single_publisher_layer):
    # just for coverage purposes
    assert isinstance(str(zmq_single_publisher_layer), str)


@pytest.mark.asyncio
async def test_new_channel(zmq_single_publisher_layer):
    # just for coverage purposes
    ch = await zmq_single_publisher_layer.new_channel()
    assert isinstance(ch, str) and "!" in ch