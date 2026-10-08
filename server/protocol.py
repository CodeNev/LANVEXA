import asyncio
import struct

HEADER = struct.Struct(">BII")

AUTH = 0x01
AUTH_OK = 0x02
AUTH_FAIL = 0x03
OPEN_STREAM = 0x10
DATA = 0x11
CLOSE_STREAM = 0x12
PING = 0x30
PONG = 0x32
ERROR = 0x41


def encode(msg_type: int, stream_id: int, payload: bytes = b"") -> bytes:
    return HEADER.pack(msg_type, stream_id, len(payload)) + payload


async def read_frame(reader: asyncio.StreamReader):
    header = await reader.readexactly(HEADER.size)
    msg_type, stream_id, length = HEADER.unpack(header)
    payload = await reader.readexactly(length) if length else b""
    return msg_type, stream_id, payload