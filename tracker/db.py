"""SQLite storage. One row per listing seen per collection run, plus run metadata."""
import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,            -- ISO UTC timestamp
    day TEXT NOT NULL,           -- YYYY-MM-DD (UTC)
    source TEXT NOT NULL         -- 'ebay' or 'sample'
);
CREATE TABLE IF NOT EXISTS listings (
    run_id INTEGER NOT NULL REFERENCES runs(id),
    model_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    title TEXT,
    bucket TEXT NOT NULL,        -- 'used' or 'new'
    price REAL NOT NULL,
    shipping REAL,
    total REAL NOT NULL,
    url TEXT,
    image TEXT,
    seller_pct REAL,
    seller_score INTEGER,
    PRIMARY KEY (run_id, model_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_listings_model ON listings(model_id, bucket);
CREATE TABLE IF NOT EXISTS summaries (
    model_id TEXT PRIMARY KEY,   -- model id, or '_market' for the homepage report
    day TEXT NOT NULL,
    text TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con
