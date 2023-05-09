import asyncio
import json
import time
import uuid

from channels.layers import BaseChannelLayer
import zmq
import zmq.asyncio


class BaseZmqChannelLayer(BaseChannelLayer):
    extensions = ['group', 'flush']
    DELIMITER = "\n"

    def __init__(self, expiry=60, capacity=100, channel_capacity=None, group_expiry=86400, **kwargs):
        super().__init__(expiry=expiry, capacity=capacity, channel_capacity=channel_capacity, **kwargs)
        self.group_expiry = group_expiry  # group expiry not implemented


class EmbeddedZmqChannelLayer(BaseZmqChannelLayer):
    """
    This is a Channels' layer implementated with ZeroMQ sockets.

    We call this implementation "embedded" because there is only one publisher process
    allowed at any point in time and this process must be the same that produces all the messages.

    This is meant to be used in a management command by calling group_send() and send()
    while the consumer threads can concurrently call receive()
    """

    def __init__(self, socket_address, expiry=60, capacity=100, channel_capacity=None, group_expiry=86400, **kwargs):
        super().__init__(expiry=expiry, capacity=capacity, channel_capacity=channel_capacity, group_expiry=group_expiry, **kwargs)

        self.zmq_socket_address = socket_address

        self.zmq_context  = zmq.asyncio.Context.instance()
        self.zmq_pub_socket: zmq.asyncio.Socket | None = None

        # a lock that must be acquired to prevent concurrent calls to send_multipart()
        self.zmq_pub_socket_lock = asyncio.Lock()

        # 1 socket is 1 channel + any number of groups
        self.zmq_sub_sockets: dict[str, zmq.asyncio.Socket] = {}
        # a lock that must be acquired to prevent concurrent operations on the sub_sockets dictionary
        self.zmq_sub_dict_lock = asyncio.Lock()
        # a group of locks that must be acquired per socket to prevent concurrent calls to recv_multipart()
        self.zmq_sub_locks: dict[str, asyncio.Lock] = {}

        # Decide on a unique client prefix to use in ! sections
        self.client_prefix = uuid.uuid4().hex

    async def send(self, channel, message):
        """
        Send a message onto a (general or specific) channel.
        """
        # Typecheck
        assert isinstance(message, dict), "message is not a dict"
        assert self.valid_channel_name(channel), "Channel name not valid"
        # If it's a process-local channel, strip off local part and stick full
        # name in message
        assert "__asgi_channel__" not in message

        channel_non_local_name = channel
        if "!" in channel:
            message = dict(message.items())
            message["__asgi_channel__"] = channel
            channel_non_local_name = self.non_local_name(channel)
        await self._do_send(channel_non_local_name, message)

    async def group_send(self, group, message):
        # Check types
        assert isinstance(message, dict), "Message is not a dict"
        assert self.valid_group_name(group), "Invalid group name"
        await self._do_send(group, message)

    async def _init_pub_socket(self):
        self.zmq_pub_socket = self.zmq_context.socket(zmq.PUB)
        self.zmq_pub_socket.set_hwm(self.capacity)
        self.zmq_pub_socket.bind(self.zmq_socket_address)

    async def _do_send(self, topic: str, message: dict):
        if self.zmq_pub_socket is None:
            await self._init_pub_socket()

        async with self.zmq_pub_socket_lock:
            await self.zmq_pub_socket.send_multipart(
                (
                    (topic + self.DELIMITER).encode(),
                    str(time.time() + self.expiry).encode(),
                    self.serialize(message)
                )
            )

    async def receive(self, channel):
        """
        Receive the first message that arrives on the channel.
        If more than one coroutine waits on the same channel, a random one
        of the waiting coroutines will get the result.
        """
        assert self.valid_channel_name(channel)
        socket = await self._get_sub_socket(channel)
        while True:
            async with self.zmq_sub_locks[channel]:
                topic, expiration_timestamp, message = await socket.recv_multipart()
            #if float(expiration_timestamp.decode()) < time.time():  # message has expired, skip to the next one
            #    continue
            return self.deserialize(message)

    async def new_channel(self, prefix="specific"):
        """
        Returns a new channel name that can be used by something in our
        process as a specific channel.
        """
        return f"{prefix}.{self.client_prefix}!{uuid.uuid4().hex}"

    # Flush extension

    async def flush(self):
        async with self.zmq_sub_dict_lock:
            for v in self.zmq_sub_sockets.values():
                v.close(0)
            self.zmq_sub_sockets = {}
            self.zmq_sub_locks = {}

    # Groups extension

    async def group_add(self, group, channel):
        """
        Adds the channel name to a group.
        """
        # Check the inputs
        assert self.valid_group_name(group), "Group name not valid"
        assert self.valid_channel_name(channel), "Channel name not valid"
        socket = await self._get_sub_socket(channel)
        socket.subscribe(group + self.DELIMITER)

    async def group_discard(self, group, channel):
        # Both should be text and valid
        assert self.valid_channel_name(channel), "Invalid channel name"
        assert self.valid_group_name(group), "Invalid group name"
        socket = await self._get_sub_socket(channel)
        socket.unsubscribe(group + self.DELIMITER)

    async def _get_sub_socket(self, channel):
        async with self.zmq_sub_dict_lock:
            if channel not in self.zmq_sub_sockets:
                socket = self.zmq_context.socket(zmq.SUB)
                socket.set_hwm(self.capacity)
                socket.connect(self.zmq_socket_address)
                socket.subscribe(channel + self.DELIMITER)
                self.zmq_sub_sockets[channel] = socket
                self.zmq_sub_locks[channel] = asyncio.Lock()
        return self.zmq_sub_sockets[channel]

    def serialize(self, message):
        """
        Serializes message to a byte string.
        """
        value = json.dumps(message).encode()
        return value

    def deserialize(self, message):
        """
        Deserializes from a byte string.
        """
        return json.loads(message)

    def __str__(self):
        return f"{self.__class__.__name__}(socket={self.zmq_socket_address})"