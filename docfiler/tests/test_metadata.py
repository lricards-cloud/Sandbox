import json

import pytest

from docfiler.metadata import parse_metadata
from docfiler.models import DocMetadata


def test_parses_full_sidecar():
    raw = json.dumps(
        {
            "type": "receipt",
            "title": "Home Depot - lumber",
            "date": "2026-08-08",
            "vendor": "Home Depot",
            "amount": "42.17",
            "currency": "usd",
            "tags": ["home-improvement", ""],
            "summary": "Receipt for lumber.",
            "source_filename": "IMG_1.jpg",
        }
    )
    meta = parse_metadata(raw)
    assert meta == DocMetadata(
        type="receipt",
        title="Home Depot - lumber",
        date="2026-08-08",
        vendor="Home Depot",
        amount=42.17,
        currency="USD",
        tags=["home-improvement"],
        summary="Receipt for lumber.",
        source_filename="IMG_1.jpg",
    )


def test_missing_required_field_raises():
    with pytest.raises(ValueError, match="missing required field"):
        parse_metadata(json.dumps({"type": "receipt", "title": "x"}))


def test_bad_date_format_raises():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_metadata(json.dumps({"type": "receipt", "title": "x", "date": "08/08/2026"}))


def test_unknown_type_falls_back_to_other():
    meta = parse_metadata(json.dumps({"type": "utility-bill", "title": "x", "date": "2026-08-08"}))
    assert meta.type == "other"


def test_defaults_when_optional_fields_absent():
    meta = parse_metadata(json.dumps({"type": "tax", "title": "W-2", "date": "2026-01-31"}))
    assert meta.vendor is None
    assert meta.amount is None
    assert meta.currency == "USD"
    assert meta.tags == []
