"""Orbit's own SQLite store (settings for alerts, push subscriptions, history, devices, metrics)."""
import json
import os
import sqlite3
import threading
from pathlib import Path

STATE = Path(os.environ.get("DASH_STATE", Path.home() / ".config" / "picommand"))
STATE.mkdir(parents=True, exist_ok=True)
DB = STATE / "orbit.db"
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS subs (endpoint TEXT PRIMARY KEY, p256dh TEXT, auth TEXT, ua TEXT, created REAL);
CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, rule TEXT, level TEXT,
    title TEXT, body TEXT, url TEXT, pushed INTEGER);
CREATE TABLE IF NOT EXISTS devices (mac TEXT PRIMARY KEY, ip TEXT, host TEXT, vendor TEXT, name TEXT,
    trusted INTEGER DEFAULT 0, first_seen REAL, last_seen REAL, iface TEXT);
CREATE TABLE IF NOT EXISTS netping (ts REAL PRIMARY KEY, ok INTEGER, ms REAL);
CREATE TABLE IF NOT EXISTS speed (ts REAL PRIMARY KEY, down REAL, up REAL, ping REAL, err TEXT);
CREATE TABLE IF NOT EXISTS hits (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, path TEXT, ref TEXT,
    visitor TEXT, status INTEGER, kind TEXT, model TEXT);
CREATE INDEX IF NOT EXISTS hits_ts ON hits(ts);
CREATE TABLE IF NOT EXISTS earnings (key TEXT PRIMARY KEY, ts REAL, amount REAL, item TEXT, imported REAL);
CREATE TABLE IF NOT EXISTS passkeys (cred_id TEXT PRIMARY KEY, x TEXT, y TEXT, sign_count INTEGER, created REAL);
"""


def connect():
    con = sqlite3.connect(DB, timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


_con = connect()


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in _con.execute(sql, args).fetchall()]


def x(sql, args=()):
    with _lock:
        cur = _con.execute(sql, args)
        _con.commit()
        return cur.lastrowid


def many(sql, rows):
    with _lock:
        _con.executemany(sql, rows)
        _con.commit()


def get(k, default=None):
    r = q("SELECT v FROM kv WHERE k=?", (k,))
    return json.loads(r[0]["v"]) if r else default


def put(k, v):
    x("INSERT OR REPLACE INTO kv VALUES (?,?)", (k, json.dumps(v)))
