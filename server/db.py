import asyncpg

from .config import settings

pool = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tunnels (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    game TEXT NOT NULL,
    protocol TEXT NOT NULL,
    local_host TEXT NOT NULL,
    local_port INTEGER NOT NULL,
    public_host TEXT NOT NULL,
    public_port INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'stopped',
    token TEXT NOT NULL UNIQUE,
    bytes_in BIGINT NOT NULL DEFAULT 0,
    bytes_out BIGINT NOT NULL DEFAULT 0,
    connections INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    tunnel_id TEXT,
    action TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tunnels_user ON tunnels(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_logs(user_id);
"""


async def init_db():
    global pool
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)


async def close_db():
    global pool
    if pool is not None:
        await pool.close()
        pool = None


def get_pool():
    return pool


async def log_activity(user_id, tunnel_id, action, status="success"):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO activity_logs (user_id, tunnel_id, action, status) VALUES ($1, $2, $3, $4)",
            user_id,
            tunnel_id,
            action,
            status,
        )