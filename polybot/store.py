"""SQLite-backed state: discovered wallets, seen trades, and copy orders.

Kept deliberately small — one connection, plain SQL, no ORM.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any

from .models import CopyOrder, WalletStats

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    address       TEXT PRIMARY KEY,
    realized_pnl  REAL,
    unrealized_pnl REAL,
    volume        REAL,
    num_trades    INTEGER,
    num_closed    INTEGER,
    num_wins      INTEGER,
    last_active   INTEGER,
    score         REAL,
    followed      INTEGER DEFAULT 0,
    updated_at    INTEGER
);

CREATE TABLE IF NOT EXISTS seen_trades (
    uid       TEXT PRIMARY KEY,
    wallet    TEXT,
    ts        INTEGER
);

CREATE TABLE IF NOT EXISTS copy_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_wallet   TEXT,
    source_trade_uid TEXT,
    asset           TEXT,
    condition_id    TEXT,
    side            TEXT,
    price           REAL,
    size            REAL,
    usdc            REAL,
    title           TEXT,
    mode            TEXT,
    status          TEXT,
    detail          TEXT,
    ts              INTEGER
);
"""


class Store:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ----- wallets -----------------------------------------------------------
    def upsert_wallet(self, s: WalletStats, followed: bool | None = None) -> None:
        existing = self.conn.execute(
            "SELECT followed FROM wallets WHERE address = ?", (s.address,)
        ).fetchone()
        follow_val = (
            int(followed)
            if followed is not None
            else (existing["followed"] if existing else 0)
        )
        self.conn.execute(
            """
            INSERT INTO wallets (address, realized_pnl, unrealized_pnl, volume,
                num_trades, num_closed, num_wins, last_active, score, followed, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(address) DO UPDATE SET
                realized_pnl=excluded.realized_pnl,
                unrealized_pnl=excluded.unrealized_pnl,
                volume=excluded.volume,
                num_trades=excluded.num_trades,
                num_closed=excluded.num_closed,
                num_wins=excluded.num_wins,
                last_active=excluded.last_active,
                score=excluded.score,
                followed=excluded.followed,
                updated_at=excluded.updated_at
            """,
            (
                s.address, s.realized_pnl, s.unrealized_pnl, s.volume,
                s.num_trades, s.num_closed, s.num_wins, s.last_active, s.score,
                follow_val, int(time.time()),
            ),
        )
        self.conn.commit()

    def set_followed(self, address: str, followed: bool) -> None:
        addr = address.lower()
        # Insert a bare row when tracking an address we haven't scored yet.
        self.conn.execute(
            "INSERT OR IGNORE INTO wallets (address, updated_at) VALUES (?, ?)",
            (addr, int(time.time())),
        )
        self.conn.execute(
            "UPDATE wallets SET followed = ? WHERE address = ?", (int(followed), addr)
        )
        self.conn.commit()

    def set_followed_top(self, n: int) -> list[str]:
        """Mark only the top-n scored wallets as followed; return their addresses."""
        self.conn.execute("UPDATE wallets SET followed = 0")
        rows = self.conn.execute(
            "SELECT address FROM wallets ORDER BY score DESC LIMIT ?", (n,)
        ).fetchall()
        addrs = [r["address"] for r in rows]
        self.conn.executemany(
            "UPDATE wallets SET followed = 1 WHERE address = ?", [(a,) for a in addrs]
        )
        self.conn.commit()
        return addrs

    def followed_wallets(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT address FROM wallets WHERE followed = 1 ORDER BY score DESC"
        ).fetchall()
        return [r["address"] for r in rows]

    def top_wallets(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM wallets ORDER BY score DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ----- seen trades (dedupe) ---------------------------------------------
    def is_seen(self, uid: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM seen_trades WHERE uid = ?", (uid,)
            ).fetchone()
            is not None
        )

    def mark_seen(self, uid: str, wallet: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_trades (uid, wallet, ts) VALUES (?,?,?)",
            (uid, wallet, int(time.time())),
        )
        self.conn.commit()

    # ----- copy orders -------------------------------------------------------
    def record_copy(self, order: CopyOrder) -> None:
        self.conn.execute(
            """
            INSERT INTO copy_orders (source_wallet, source_trade_uid, asset,
                condition_id, side, price, size, usdc, title, mode, status, detail, ts)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                order.source_wallet, order.source_trade_uid, order.asset,
                order.condition_id, order.side, order.price, order.size, order.usdc,
                order.title, order.mode, order.status, order.detail, order.ts,
            ),
        )
        self.conn.commit()

    def recent_copies(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM copy_orders ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def open_exposure(self) -> dict[str, float]:
        """Net USDC exposure per market from recorded fills (BUY +, SELL -)."""
        rows = self.conn.execute(
            """
            SELECT condition_id,
                   SUM(CASE WHEN side='BUY' THEN usdc ELSE -usdc END) AS net
            FROM copy_orders WHERE status IN ('filled','submitted')
            GROUP BY condition_id
            """
        ).fetchall()
        return {r["condition_id"]: float(r["net"] or 0.0) for r in rows}

    def realized_pnl_since(self, ts: int) -> float:
        """Crude realized PnL proxy: net SELL minus BUY usdc since `ts`."""
        row = self.conn.execute(
            """
            SELECT SUM(CASE WHEN side='SELL' THEN usdc ELSE -usdc END) AS pnl
            FROM copy_orders WHERE status='filled' AND ts >= ?
            """,
            (ts,),
        ).fetchone()
        return float(row["pnl"] or 0.0)
