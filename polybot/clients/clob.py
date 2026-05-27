"""Thin wrapper over the Polymarket CLOB.

Two responsibilities:
  * Read market prices (works without any credentials) for paper fills and
    slippage checks.
  * Place real orders in live mode via `py-clob-client` (imported lazily so the
    dependency is only needed when actually trading).
"""
from __future__ import annotations

import logging
from typing import Any

from ..config import Secrets
from .http import HttpClient

CLOB_HOST = "https://clob.polymarket.com"
POLYGON_CHAIN_ID = 137

log = logging.getLogger("polybot.clob")


class ClobClient:
    def __init__(self, secrets: Secrets | None = None, host: str = CLOB_HOST):
        self.host = host
        self.secrets = secrets or Secrets()
        self.http = HttpClient(host)
        self._signed: Any = None  # lazily-built py_clob_client instance

    # ----- market data (no auth) --------------------------------------------
    def price(self, token_id: str, side: str = "BUY") -> float | None:
        """Best executable price for `side` on a token.

        For a BUY we look at the ask; for a SELL, the bid.
        """
        book_side = "buy" if side.upper() == "BUY" else "sell"
        data = self.http.get("/price", params={"token_id": token_id, "side": book_side})
        if isinstance(data, dict) and "price" in data:
            try:
                return float(data["price"])
            except (TypeError, ValueError):
                return None
        return None

    def midpoint(self, token_id: str) -> float | None:
        data = self.http.get("/midpoint", params={"token_id": token_id})
        if isinstance(data, dict) and "mid" in data:
            try:
                return float(data["mid"])
            except (TypeError, ValueError):
                return None
        return None

    # ----- live trading (auth) ----------------------------------------------
    def _ensure_signed(self) -> Any:
        if self._signed is not None:
            return self._signed
        if not self.secrets.has_trading_key:
            raise RuntimeError(
                "Live trading requires POLYMARKET_PRIVATE_KEY in the environment."
            )
        try:
            from py_clob_client.client import ClobClient as _PyClob  # type: ignore
            from py_clob_client.clob_types import ApiCreds  # type: ignore
        except ImportError as err:  # pragma: no cover - exercised only live
            raise RuntimeError(
                "Live mode needs the 'py-clob-client' package: pip install py-clob-client"
            ) from err

        kwargs: dict[str, Any] = {
            "host": self.host,
            "key": self.secrets.private_key,
            "chain_id": POLYGON_CHAIN_ID,
        }
        if self.secrets.funder_address:
            # Polymarket proxy/relayer signature type.
            kwargs["signature_type"] = 1
            kwargs["funder"] = self.secrets.funder_address

        client = _PyClob(**kwargs)

        if self.secrets.clob_api_key and self.secrets.clob_api_secret:
            client.set_api_creds(
                ApiCreds(
                    api_key=self.secrets.clob_api_key,
                    api_secret=self.secrets.clob_api_secret,
                    api_passphrase=self.secrets.clob_api_passphrase or "",
                )
            )
        else:
            # Derive (and cache for the process) L2 creds from the key.
            client.set_api_creds(client.create_or_derive_api_creds())

        self._signed = client
        return client

    def place_limit_order(
        self, token_id: str, side: str, price: float, size_shares: float
    ) -> dict[str, Any]:
        """Place a marketable limit order. Returns the raw CLOB response.

        `size_shares` is the number of outcome shares (USDC = price * shares).
        """
        client = self._ensure_signed()
        from py_clob_client.clob_types import OrderArgs  # type: ignore
        from py_clob_client.order_builder.constants import BUY, SELL  # type: ignore

        order = client.create_order(
            OrderArgs(
                token_id=token_id,
                price=round(float(price), 4),
                size=round(float(size_shares), 2),
                side=BUY if side.upper() == "BUY" else SELL,
            )
        )
        resp = client.post_order(order)
        return resp if isinstance(resp, dict) else {"response": resp}
