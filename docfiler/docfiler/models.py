"""Core data types for docfiler."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

VALID_TYPES = (
    "receipt",
    "medical",
    "tax",
    "warranty",
    "legal",
    "insurance",
    "statement",
    "other",
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class DocMetadata:
    """The classification Zapier's AI step produces for one document.

    Mirrors the JSON sidecar contract in docs/METADATA_SCHEMA.md.
    """

    type: str
    title: str
    date: str  # ISO YYYY-MM-DD
    vendor: str | None = None
    amount: float | None = None
    currency: str = "USD"
    tags: list[str] = field(default_factory=list)
    summary: str | None = None
    source_filename: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "DocMetadata":
        missing = [k for k in ("type", "title", "date") if not data.get(k)]
        if missing:
            raise ValueError(f"metadata missing required field(s): {', '.join(missing)}")

        date = str(data["date"]).strip()
        if not _DATE_RE.match(date):
            raise ValueError(f"metadata 'date' must be YYYY-MM-DD, got {date!r}")

        doc_type = str(data["type"]).strip().lower()
        if doc_type not in VALID_TYPES:
            doc_type = "other"

        amount = data.get("amount")
        return cls(
            type=doc_type,
            title=str(data["title"]).strip(),
            date=date,
            vendor=(str(data["vendor"]).strip() if data.get("vendor") else None),
            amount=(float(amount) if amount not in (None, "") else None),
            currency=str(data.get("currency") or "USD").upper(),
            tags=[str(t).strip() for t in (data.get("tags") or []) if str(t).strip()],
            summary=(str(data["summary"]).strip() if data.get("summary") else None),
            source_filename=data.get("source_filename") or None,
        )
