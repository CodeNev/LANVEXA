import asyncio
import contextlib
import json
import logging
from typing import Dict

from . import db as db_module
from .config import settings
from .protocol import (
    AUTH,
    AUTH_FAIL,
    AUTH_OK,
    CLOSE_STREAM,
    DATA,
    OPEN_STREAM,
    PING,
    PONG,
    encode,
    read_frame,
)

log = logging.getLogger("lanvexa.relay")


class TunnelConnection:
    def __init__(self, tunnel_id, reader, writer):
        self.tunnel_id = tunnel_id
        self.reader = reader
        self.writer = writer
        self.streams: Dict[int, asyncio.StreamWriter] = {}
        self.next_stream_id = 1
        self.lock = asyncio.Lock()

    async def send(self, msg_type, stream_id, payload=b""):
        self.writer.write(encode(msg_type, stream_id, payload))
        await self.writer.drain()

    async def allocate_stream(self):
        async with self.lock:
            sid = self.next_stream_id
            self.next_stream_id = (self.next_stream_id % 0x7FFFFFFF) + 1
            return sid


class Relay:
    def __init__(self):
        self.tunnels: Dict[str, TunnelConnection] = {}
        self.port_to_tunnel: Dict[int, str] = {}
        self.tcp_listeners: Dict[int, asyncio.AbstractServer] = {}

    async def start_control(self):
        server = await asyncio.start_server(
            self.handle_control,
            settings.relay_host,
            settings.relay_control_port,
        )
        log.info("relay control listening on %s:%s", settings.relay_host, settings.relay_control_port)
        return server

    async def handle_control(self, reader, writer):
        try:
            msg_type, _, payload = await read_frame(reader)
            if msg_type != AUTH:
                writer.close()
                return
            data = json.loads(payload.decode("utf-8"))
            token = data.get("token", "")
        except Exception:
            writer.close()
            return

        async with db_module.get_pool().acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tunnels WHERE token = $1", token)

        if row is None:
            writer.write(encode(AUTH_FAIL, 0, b'{"error":"invalid_token"}'))
            await writer.drain()
            writer.close()
            return

        tunnel = dict(row)
        tunnel_id = tunnel["id"]

        writer.write(encode(AUTH_OK, 0, json.dumps({"tunnel_id": tunnel_id}).encode()))
        await writer.drain()

        existing = self.tunnels.get(tunnel_id)
        if existing is not None:
            with contextlib.suppress(Exception):
                existing.writer.close()

        conn = TunnelConnection(tunnel_id, reader, writer)
        self.tunnels[tunnel_id] = conn
        await self.open_public_listener(tunnel)

        async with db_module.get_pool().acquire() as db_conn:
            await db_conn.execute(
                "UPDATE tunnels SET status = 'online', last_seen = NOW() WHERE id = $1",
                tunnel_id,
            )
        await db_module.log_activity(tunnel["user_id"], tunnel_id, "tunnel.online")

        try:
            await self.pump_client(conn)
        finally:
            await self.teardown_tunnel(tunnel_id)

    async def pump_client(self, conn):
        try:
            while True:
                msg_type, stream_id, payload = await read_frame(conn.reader)
                if msg_type == DATA:
                    target = conn.streams.get(stream_id)
                    if target is not None:
                        target.write(payload)
                        with contextlib.suppress(Exception):
                            await target.drain()
                elif msg_type == CLOSE_STREAM:
                    target = conn.streams.pop(stream_id, None)
                    if target is not None:
                        with contextlib.suppress(Exception):
                            target.close()
                elif msg_type == PING:
                    await conn.send(PONG, 0)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        except Exception as exc:
            log.warning("client pump error: %s", exc)

    async def open_public_listener(self, tunnel):
        port = tunnel["public_port"]
        if port in self.tcp_listeners:
            return
        if "tcp" not in tunnel["protocol"]:
            return

        listener = await asyncio.start_server(
            lambda r, w, p=port: self.handle_public_tcp(p, r, w),
            settings.relay_host,
            port,
        )
        self.tcp_listeners[port] = listener
        self.port_to_tunnel[port] = tunnel["id"]
        log.info("tcp listener on %s:%s for tunnel %s", settings.relay_host, port, tunnel["id"])

    async def handle_public_tcp(self, port, reader, writer):
        tunnel_id = self.port_to_tunnel.get(port)
        if tunnel_id is None:
            writer.close()
            return
        conn = self.tunnels.get(tunnel_id)
        if conn is None:
            writer.close()
            return

        stream_id = await conn.allocate_stream()
        conn.streams[stream_id] = writer
        try:
            await conn.send(OPEN_STREAM, stream_id)
        except Exception:
            conn.streams.pop(stream_id, None)
            writer.close()
            return

        async with db_module.get_pool().acquire() as db_conn:
            await db_conn.execute(
                "UPDATE tunnels SET connections = connections + 1 WHERE id = $1",
                tunnel_id,
            )
        await db_module.log_activity(None, tunnel_id, "connection.opened")

        try:
            while True:
                chunk = await reader.read(16384)
                if not chunk:
                    break
                await conn.send(DATA, stream_id, chunk)
        except Exception:
            pass
        finally:
            conn.streams.pop(stream_id, None)
            with contextlib.suppress(Exception):
                await conn.send(CLOSE_STREAM, stream_id)
            with contextlib.suppress(Exception):
                writer.close()

            async with db_module.get_pool().acquire() as db_conn:
                await db_conn.execute(
                    "UPDATE tunnels SET connections = GREATEST(connections - 1, 0) WHERE id = $1",
                    tunnel_id,
                )
            await db_module.log_activity(None, tunnel_id, "connection.closed")

    async def teardown_tunnel(self, tunnel_id):
        conn = self.tunnels.pop(tunnel_id, None)
        port = None
        for p, tid in list(self.port_to_tunnel.items()):
            if tid == tunnel_id:
                port = p
                del self.port_to_tunnel[p]
                break

        if port is not None:
            listener = self.tcp_listeners.pop(port, None)
            if listener is not None:
                listener.close()
                with contextlib.suppress(Exception):
                    await listener.wait_closed()

        if conn is not None:
            for w in conn.streams.values():
                with contextlib.suppress(Exception):
                    w.close()
            with contextlib.suppress(Exception):
                conn.writer.close()

        async with db_module.get_pool().acquire() as db_conn:
            await db_conn.execute("UPDATE tunnels SET status = 'offline' WHERE id = $1", tunnel_id)
        await db_module.log_activity(None, tunnel_id, "tunnel.offline")

        log.info("tunnel %s torn down", tunnel_id)


relay = Relay()


async def allocate_port() -> int:
    used = set(relay.port_to_tunnel.keys())
    async with db_module.get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT public_port FROM tunnels")
        used.update(r["public_port"] for r in rows)

    for candidate in range(settings.port_range_start, settings.port_range_end + 1):
        if candidate not in used:
            return candidate
    raise RuntimeError("no_free_port")