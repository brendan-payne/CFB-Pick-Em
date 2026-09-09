from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "pickem.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS players (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weeks (
  id TEXT PRIMARY KEY,
  season INTEGER NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL,
  sort_order INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'upcoming',
  lock_at TEXT
);

CREATE TABLE IF NOT EXISTS games (
  id TEXT PRIMARY KEY,
  week_id TEXT NOT NULL REFERENCES weeks(id),
  label TEXT NOT NULL,
  away_team TEXT NOT NULL,
  home_team TEXT NOT NULL,
  espn_event_id TEXT,
  espn_url TEXT,
  away_espn_id TEXT,
  home_espn_id TEXT,
  away_logo TEXT,
  home_logo TEXT,
  away_rank INTEGER,
  home_rank INTEGER,
  spread TEXT,
  kickoff TEXT,
  is_auburn INTEGER NOT NULL DEFAULT 0,
  point_value INTEGER NOT NULL DEFAULT 5,
  winner TEXT,
  status TEXT NOT NULL DEFAULT 'scheduled',
  away_score INTEGER,
  home_score INTEGER,
  short_detail TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS picks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT NOT NULL REFERENCES players(id),
  game_id TEXT NOT NULL REFERENCES games(id),
  picked_team TEXT NOT NULL,
  submitted_at TEXT NOT NULL,
  UNIQUE (player_id, game_id)
);

CREATE TABLE IF NOT EXISTS preseason_picks (
  player_id TEXT PRIMARY KEY REFERENCES players(id),
  auburn_record TEXT,
  big10 TEXT,
  big12 TEXT,
  acc TEXT,
  sec TEXT,
  playoff_teams TEXT NOT NULL,
  national_champion TEXT,
  submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(weeks)")}
        if "lock_at" not in cols:
            conn.execute("ALTER TABLE weeks ADD COLUMN lock_at TEXT")


def rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def row(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict | None:
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None
