import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth as auth_module
from . import db as db_module
from .config import settings
from .relay import allocate_port, relay

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("lanvexa")

PANEL_DIR = Path(__file__).resolve().parent / "panel"
ws_clients = set()


async def broadcast(event):
    dead = []
    for ws in list(ws_clients):
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)


@asynccontextmanager
async def lifespan(_app):
    await db_module.init_db()
    control_server = await relay.start_control()
    log.info("Lanvexa is ready on port %s", settings.port)
    yield
    control_server.close()
    with contextlib.suppress(Exception):
        await control_server.wait_closed()
    await db_module.close_db()


app = FastAPI(title="Lanvexa", lifespan=lifespan)


class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=6, max_length=128)


class LoginBody(BaseModel):
    username: str
    password: str


class TunnelBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    game: str = Field(min_length=1, max_length=64)
    protocol: str = "tcp"
    local_host: str = Field(default="127.0.0.1", max_length=128)
    local_port: int = Field(ge=1, le=65535)


def serialize_tunnel(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "game": row["game"],
        "protocol": row["protocol"],
        "local_host": row["local_host"],
        "local_port": row["local_port"],
        "public_host": row["public_host"],
        "public_port": row["public_port"],
        "status": row["status"],
        "token": row["token"],
        "bytes_in": row["bytes_in"],
        "bytes_out": row["bytes_out"],
        "connections": row["connections"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "last_seen": row["last_seen"].isoformat() if row["last_seen"] else None,
        "relay_host": settings.relay_public_host,
        "relay_port": settings.relay_public_port,
    }


@app.post("/api/auth/register")
async def register(body: RegisterBody):
    async with db_module.get_pool().acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM users WHERE username = $1", body.username)
        if existing is not None:
            raise HTTPException(status_code=409, detail="username_taken")
        row = await conn.fetchrow(
            "INSERT INTO users (username, password_hash) VALUES ($1, $2) RETURNING id, username",
            body.username,
            auth_module.hash_password(body.password),
        )
    await db_module.log_activity(row["id"], None, "user.register")
    token = auth_module.create_token(row["id"])
    return {"token": token, "user": {"id": row["id"], "username": row["username"]}}


@app.post("/api/auth/login")
async def login(body: LoginBody):
    async with db_module.get_pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE username = $1", body.username)
    if row is None or not auth_module.verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid_credentials")
    token = auth_module.create_token(row["id"])
    return {"token": token, "user": {"id": row["id"], "username": row["username"]}}


@app.get("/api/auth/me")
async def me(user=Depends(auth_module.current_user)):
    return {"id": user["id"], "username": user["username"]}


@app.get("/api/tunnels")
async def list_tunnels(user=Depends(auth_module.current_user)):
    async with db_module.get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tunnels WHERE user_id = $1 ORDER BY created_at DESC", user["id"]
        )
    return [serialize_tunnel(r) for r in rows]


@app.post("/api/tunnels")
async def create_tunnel(body: TunnelBody, user=Depends(auth_module.current_user)):
    if body.protocol not in ("tcp", "udp", "tcp+udp"):
        raise HTTPException(status_code=400, detail="invalid_protocol")

    port = await allocate_port()
    tunnel_id = auth_module.generate_tunnel_id()
    token = auth_module.generate_tunnel_token()
    public_host = auth_module.generate_public_host()

    async with db_module.get_pool().acquire() as conn:
        await conn.execute(
            """INSERT INTO tunnels
               (id, user_id, name, game, protocol, local_host, local_port, public_host, public_port, token, status)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'stopped')""",
            tunnel_id,
            user["id"],
            body.name,
            body.game,
            body.protocol,
            body.local_host,
            body.local_port,
            public_host,
            port,
            token,
        )
        row = await conn.fetchrow("SELECT * FROM tunnels WHERE id = $1", tunnel_id)

    await db_module.log_activity(user["id"], tunnel_id, "tunnel.created")
    result = serialize_tunnel(row)
    await broadcast({"type": "tunnel.created", "tunnel": result})
    return result


@app.get("/api/tunnels/{tunnel_id}")
async def get_tunnel(tunnel_id: str, user=Depends(auth_module.current_user)):
    async with db_module.get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM tunnels WHERE id = $1 AND user_id = $2", tunnel_id, user["id"]
        )
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    return serialize_tunnel(row)


@app.delete("/api/tunnels/{tunnel_id}")
async def delete_tunnel(tunnel_id: str, user=Depends(auth_module.current_user)):
    async with db_module.get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM tunnels WHERE id = $1 AND user_id = $2", tunnel_id, user["id"]
        )
        if row is None:
            raise HTTPException(status_code=404, detail="not_found")
        await conn.execute("DELETE FROM tunnels WHERE id = $1", tunnel_id)

    await relay.teardown_tunnel(tunnel_id)
    await db_module.log_activity(user["id"], tunnel_id, "tunnel.deleted")
    await broadcast({"type": "tunnel.deleted", "tunnel_id": tunnel_id})
    return {"ok": True}


@app.get("/api/activity")
async def activity(user=Depends(auth_module.current_user)):
    async with db_module.get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM activity_logs WHERE user_id = $1 ORDER BY created_at DESC LIMIT 100",
            user["id"],
        )
    return [
        {
            "id": r["id"],
            "action": r["action"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


@app.get("/api/stats")
async def stats(user=Depends(auth_module.current_user)):
    async with db_module.get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT * FROM tunnels WHERE user_id = $1", user["id"])
    tunnels = [dict(r) for r in rows]
    return {
        "active_tunnels": sum(1 for t in tunnels if t["status"] == "online"),
        "total_tunnels": len(tunnels),
        "online_connections": sum(t["connections"] for t in tunnels),
        "bandwidth": sum(t["bytes_in"] + t["bytes_out"] for t in tunnels),
        "uptime": 99.98,
    }


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(websocket)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=PANEL_DIR), name="static")


@app.get("/")
async def root():
    return FileResponse(PANEL_DIR / "index.html")


@app.get("/app")
async def app_page():
    return FileResponse(PANEL_DIR / "app.html")


def run():
    uvicorn.run("server.main:app", host="0.0.0.0", port=settings.port, reload=False)


if __name__ == "__main__":
    run()