"""Filename/slug conventions shared by the Drive filer and the Obsidian filer."""
from __future__ import annotations

import re

from .models import DocMetadata

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug or "untitled"


def base_filename(meta: DocMetadata) -> str:
    """YYYY-MM-DD_vendor-or-type_title-slug.

    e.g. 2026-08-08_home-depot_lumber-and-screws
    """
    parts = [meta.date, slugify(meta.vendor or meta.type), slugify(meta.title)]
    return "_".join(p for p in parts if p)
