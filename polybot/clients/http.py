"""A small resilient JSON-over-HTTP helper with retry/backoff."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger("polybot.http")


class HttpClient:
    def __init__(self, base_url: str = "", timeout: float = 10.0, retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "polybot/0.1 (+copytrader)"})

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        backoff = 1.0
        last_err: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    # Rate limited — honour Retry-After when present.
                    wait = float(resp.headers.get("Retry-After", backoff))
                    log.warning("429 from %s, sleeping %.1fs", url, wait)
                    time.sleep(wait)
                    backoff *= 2
                    continue
                resp.raise_for_status()
                if not resp.content:
                    return None
                return resp.json()
            except (requests.RequestException, ValueError) as err:
                last_err = err
                log.debug("GET %s failed (attempt %d/%d): %s", url, attempt, self.retries, err)
                if attempt < self.retries:
                    time.sleep(backoff)
                    backoff *= 2
        log.warning("GET %s gave up after %d attempts: %s", url, self.retries, last_err)
        return None
