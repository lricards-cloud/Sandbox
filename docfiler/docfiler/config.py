"""Configuration loading and typed accessors.

Config is a plain dict loaded from YAML, merged over built-in defaults so a
sparse user file still produces a complete, valid configuration.
"""
from __future__ import annotations

import copy
import os
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "drive": {
        "credentials_file": "service-account.json",
        "inbox_folder_id": "",
        "done_folder_id": "",
    },
    "obsidian": {
        "vault_path": "",
        "filing_root": "Filing",
        "attachments_dirname": "_attachments",
    },
    "categories": {
        "receipt": "Receipts",
        "medical": "Medical",
        "tax": "Tax",
        "warranty": "Warranties",
        "legal": "Legal",
        "insurance": "Insurance",
        "statement": "Statements",
        "other": "Other",
    },
    "poll": {
        "interval_sec": 120,
        "state_file": "docfiler_state.json",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    """Dict-backed config with convenient section accessors."""

    def __init__(self, data: dict[str, Any]):
        self.data = data

    @classmethod
    def load(cls, path: str | None) -> "Config":
        user: dict[str, Any] = {}
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                user = yaml.safe_load(fh) or {}
        return cls(_deep_merge(DEFAULTS, user))

    @property
    def drive(self) -> dict[str, Any]:
        return self.data["drive"]

    @property
    def obsidian(self) -> dict[str, Any]:
        return self.data["obsidian"]

    @property
    def categories(self) -> dict[str, str]:
        return self.data["categories"]

    @property
    def poll(self) -> dict[str, Any]:
        return self.data["poll"]
