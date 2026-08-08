"""Polls the Drive inbox folder, pairs each document with its metadata
sidecar, and files the Obsidian copy for anything not seen before.

A "pair" is two files in the inbox sharing the same stem: the document
itself (image/pdf) and a `<stem>.json` metadata sidecar. Both must be
present before a document is processed; an unpaired file is left alone and
retried on the next poll (Zapier's two upload steps aren't atomic).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .drive_client import DriveClient, DriveFile
from .metadata import parse_metadata
from .obsidian_filer import ObsidianFiler

logger = logging.getLogger(__name__)


class ProcessedState:
    """Tracks Drive file IDs already filed, so restarts don't reprocess."""

    def __init__(self, path: str):
        self.path = Path(path)
        self._seen: set[str] = set()
        if self.path.exists():
            self._seen = set(json.loads(self.path.read_text(encoding="utf-8")))

    def __contains__(self, file_id: str) -> bool:
        return file_id in self._seen

    def mark(self, *file_ids: str) -> None:
        self._seen.update(file_ids)
        self.path.write_text(json.dumps(sorted(self._seen)), encoding="utf-8")


class Poller:
    def __init__(
        self,
        drive: DriveClient,
        filer: ObsidianFiler,
        inbox_folder_id: str,
        done_folder_id: str | None,
        state: ProcessedState,
    ):
        self.drive = drive
        self.filer = filer
        self.inbox_folder_id = inbox_folder_id
        self.done_folder_id = done_folder_id
        self.state = state

    def run_once(self) -> int:
        """Process every unseen, complete (doc + sidecar) pair. Returns count filed."""
        files = [f for f in self.drive.list_folder(self.inbox_folder_id) if f.id not in self.state]
        pairs = _pair_files(files)

        filed = 0
        for content_file, sidecar_file in pairs.values():
            try:
                self._process_pair(content_file, sidecar_file)
                filed += 1
            except Exception:
                logger.exception(
                    "Failed to file %s (sidecar %s); leaving in inbox for retry",
                    content_file.name,
                    sidecar_file.name,
                )
        return filed

    def run_forever(self, interval_sec: int) -> None:
        while True:
            n = self.run_once()
            if n:
                logger.info("Filed %d document(s)", n)
            time.sleep(interval_sec)

    def _process_pair(self, content_file: DriveFile, sidecar_file: DriveFile) -> None:
        meta = parse_metadata(self.drive.download(sidecar_file.id))
        content = self.drive.download(content_file.id)
        extension = content_file.name.rsplit(".", 1)[-1] if "." in content_file.name else "bin"
        drive_url = self.drive.file_url(content_file.id)

        self.filer.file(meta, content, extension, drive_url=drive_url)

        if self.done_folder_id:
            self.drive.move(content_file.id, self.done_folder_id, self.inbox_folder_id)
            self.drive.move(sidecar_file.id, self.done_folder_id, self.inbox_folder_id)
        else:
            self.drive.delete(content_file.id)
            self.drive.delete(sidecar_file.id)

        self.state.mark(content_file.id, sidecar_file.id)


def _pair_files(files: list[DriveFile]) -> dict[str, tuple[DriveFile, DriveFile]]:
    by_stem: dict[str, dict[str, DriveFile]] = {}
    for f in files:
        stem, _, ext = f.name.rpartition(".")
        stem = stem or f.name
        slot = by_stem.setdefault(stem, {})
        slot["sidecar" if ext.lower() == "json" else "content"] = f

    return {
        stem: (slot["content"], slot["sidecar"])
        for stem, slot in by_stem.items()
        if "content" in slot and "sidecar" in slot
    }
