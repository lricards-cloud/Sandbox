"""Parses the JSON sidecar Zapier's AI step writes alongside each filed
document. See docs/METADATA_SCHEMA.md for the contract.
"""
from __future__ import annotations

import json

from .models import DocMetadata


def parse_metadata(raw: bytes | str) -> DocMetadata:
    data = json.loads(raw)
    return DocMetadata.from_dict(data)
