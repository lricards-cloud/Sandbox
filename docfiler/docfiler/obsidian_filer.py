"""Writes the Obsidian half of a filed document: an attachment plus a
markdown note with frontmatter, laid out as

    <vault>/<filing_root>/<Category>/<Year>/<base>.md
    <vault>/<filing_root>/<Category>/<Year>/<attachments_dirname>/<base>.<ext>

The Google Drive copy is filed separately (by the Zapier side of the
pipeline); this class only owns the vault-side copy.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import yaml

from .models import DocMetadata
from .naming import base_filename

DEFAULT_CATEGORIES = {
    "receipt": "Receipts",
    "medical": "Medical",
    "tax": "Tax",
    "warranty": "Warranties",
    "legal": "Legal",
    "insurance": "Insurance",
    "statement": "Statements",
    "other": "Other",
}


@dataclass
class FiledNote:
    note_path: Path
    attachment_path: Path


class ObsidianFiler:
    def __init__(
        self,
        vault_path: str,
        filing_root: str = "Filing",
        attachments_dirname: str = "_attachments",
        categories: dict[str, str] | None = None,
    ):
        self.vault_path = Path(vault_path)
        self.filing_root = filing_root
        self.attachments_dirname = attachments_dirname
        self.categories = categories or DEFAULT_CATEGORIES

    def category_dir(self, meta: DocMetadata) -> Path:
        year = meta.date.split("-")[0] if "-" in meta.date else str(dt.date.today().year)
        category = self.categories.get(meta.type) or self.categories.get("other", "Other")
        return self.vault_path / self.filing_root / category / year

    def file(
        self,
        meta: DocMetadata,
        content: bytes,
        extension: str,
        drive_url: str | None = None,
    ) -> FiledNote:
        """Write the attachment + note for one document. Returns the paths written."""
        target_dir = self.category_dir(meta)
        attach_dir = target_dir / self.attachments_dirname
        attach_dir.mkdir(parents=True, exist_ok=True)

        stem = base_filename(meta)
        attachment_path = attach_dir / f"{stem}.{extension.lstrip('.')}"
        attachment_path.write_bytes(content)

        note_path = target_dir / f"{stem}.md"
        note_path.write_text(self._render_note(meta, attachment_path, drive_url), encoding="utf-8")
        return FiledNote(note_path=note_path, attachment_path=attachment_path)

    def _render_note(self, meta: DocMetadata, attachment_path: Path, drive_url: str | None) -> str:
        tags = list(dict.fromkeys([meta.type, *meta.tags]))
        frontmatter = {
            "type": meta.type,
            "date": meta.date,
            "title": meta.title,
            "vendor": meta.vendor,
            "amount": meta.amount,
            "currency": meta.currency if meta.amount is not None else None,
            "tags": tags,
            "source": "gdrive",
            "drive_url": drive_url,
            "status": "filed",
            "filed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        frontmatter = {k: v for k, v in frontmatter.items() if v not in (None, [], "")}
        fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()

        lines = ["---", fm_yaml, "---", "", f"# {meta.title}", "", f"![[{attachment_path.name}]]"]
        if meta.summary:
            lines += ["", meta.summary]
        return "\n".join(lines) + "\n"
