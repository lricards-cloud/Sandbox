"""Thin Google Drive v3 wrapper — only the handful of calls docfiler needs:
listing the inbox folder, downloading a file's bytes, and moving/deleting
processed files.

Requires google-api-python-client + a service account key (see
docs/ZAPIER_SETUP.md for how to create one and share the inbox folder with
its service-account email). The google-api-python-client import is deferred
to __init__ so the rest of the package (and its tests) don't need that
dependency installed.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

DEFAULT_SCOPES = ("https://www.googleapis.com/auth/drive",)


@dataclass
class DriveFile:
    id: str
    name: str
    mime_type: str


class DriveClient:
    def __init__(self, credentials_file: str, scopes: tuple[str, ...] = DEFAULT_SCOPES):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=list(scopes)
        )
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)

    def list_folder(self, folder_id: str) -> list[DriveFile]:
        files: list[DriveFile] = []
        page_token = None
        query = f"'{folder_id}' in parents and trashed = false"
        while True:
            resp = (
                self._service.files()
                .list(q=query, fields="nextPageToken, files(id, name, mimeType)", pageToken=page_token)
                .execute()
            )
            files += [DriveFile(f["id"], f["name"], f["mimeType"]) for f in resp.get("files", [])]
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return files

    def download(self, file_id: str) -> bytes:
        from googleapiclient.http import MediaIoBaseDownload

        request = self._service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue()

    def move(self, file_id: str, new_parent_id: str, old_parent_id: str) -> None:
        self._service.files().update(
            fileId=file_id,
            addParents=new_parent_id,
            removeParents=old_parent_id,
            fields="id, parents",
        ).execute()

    def delete(self, file_id: str) -> None:
        self._service.files().delete(fileId=file_id).execute()

    def file_url(self, file_id: str) -> str:
        return f"https://drive.google.com/file/d/{file_id}/view"
