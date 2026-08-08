import json

from docfiler.drive_client import DriveFile
from docfiler.obsidian_filer import ObsidianFiler
from docfiler.poller import Poller, ProcessedState


class FakeDrive:
    """Stand-in Drive client backed by an in-memory folder listing."""

    def __init__(self, files, contents):
        self.files = list(files)
        self.contents = dict(contents)
        self.moved = []
        self.deleted = []

    def list_folder(self, folder_id):
        return list(self.files)

    def download(self, file_id):
        return self.contents[file_id]

    def move(self, file_id, new_parent_id, old_parent_id):
        self.moved.append((file_id, new_parent_id, old_parent_id))

    def delete(self, file_id):
        self.deleted.append(file_id)

    def file_url(self, file_id):
        return f"https://drive.example/{file_id}"


def _sidecar_bytes(**over):
    data = {"type": "receipt", "title": "Lumber", "date": "2026-08-08", "vendor": "Home Depot"}
    data.update(over)
    return json.dumps(data).encode()


def _poller(tmp_path, drive, done_folder_id="done-folder"):
    filer = ObsidianFiler(vault_path=str(tmp_path / "vault"))
    state = ProcessedState(str(tmp_path / "state.json"))
    return Poller(
        drive=drive,
        filer=filer,
        inbox_folder_id="inbox-folder",
        done_folder_id=done_folder_id,
        state=state,
    )


def test_files_a_complete_pair_and_moves_it_to_done(tmp_path):
    drive = FakeDrive(
        files=[
            DriveFile("content-1", "2026-08-08_lumber.jpg", "image/jpeg"),
            DriveFile("sidecar-1", "2026-08-08_lumber.json", "application/json"),
        ],
        contents={"content-1": b"fake-image-bytes", "sidecar-1": _sidecar_bytes()},
    )
    poller = _poller(tmp_path, drive)

    filed = poller.run_once()

    assert filed == 1
    note = tmp_path / "vault" / "Filing" / "Receipts" / "2026" / "2026-08-08_home-depot_lumber.md"
    assert note.exists()
    assert ("content-1", "done-folder", "inbox-folder") in drive.moved
    assert ("sidecar-1", "done-folder", "inbox-folder") in drive.moved
    assert "content-1" in poller.state
    assert "sidecar-1" in poller.state


def test_unpaired_file_is_left_for_retry(tmp_path):
    drive = FakeDrive(
        files=[DriveFile("content-1", "2026-08-08_lumber.jpg", "image/jpeg")],
        contents={"content-1": b"fake-image-bytes"},
    )
    poller = _poller(tmp_path, drive)

    filed = poller.run_once()

    assert filed == 0
    assert not drive.moved
    assert "content-1" not in poller.state


def test_already_seen_pair_is_not_reprocessed(tmp_path):
    drive = FakeDrive(
        files=[
            DriveFile("content-1", "2026-08-08_lumber.jpg", "image/jpeg"),
            DriveFile("sidecar-1", "2026-08-08_lumber.json", "application/json"),
        ],
        contents={"content-1": b"fake-image-bytes", "sidecar-1": _sidecar_bytes()},
    )
    poller = _poller(tmp_path, drive)
    assert poller.run_once() == 1

    # Drive still lists them (move didn't actually remove them from the fake's list);
    # a second poll must skip via the persisted state, not reprocess.
    assert poller.run_once() == 0


def test_malformed_sidecar_does_not_crash_the_batch(tmp_path):
    drive = FakeDrive(
        files=[
            DriveFile("bad-content", "broken.jpg", "image/jpeg"),
            DriveFile("bad-sidecar", "broken.json", "application/json"),
            DriveFile("content-1", "2026-08-08_lumber.jpg", "image/jpeg"),
            DriveFile("sidecar-1", "2026-08-08_lumber.json", "application/json"),
        ],
        contents={
            "bad-content": b"x",
            "bad-sidecar": b"not valid json",
            "content-1": b"fake-image-bytes",
            "sidecar-1": _sidecar_bytes(),
        },
    )
    poller = _poller(tmp_path, drive)

    filed = poller.run_once()

    assert filed == 1
    assert "bad-content" not in poller.state
    assert "content-1" in poller.state


def test_no_done_folder_deletes_instead_of_moving(tmp_path):
    drive = FakeDrive(
        files=[
            DriveFile("content-1", "2026-08-08_lumber.jpg", "image/jpeg"),
            DriveFile("sidecar-1", "2026-08-08_lumber.json", "application/json"),
        ],
        contents={"content-1": b"fake-image-bytes", "sidecar-1": _sidecar_bytes()},
    )
    poller = _poller(tmp_path, drive, done_folder_id=None)

    assert poller.run_once() == 1
    assert not drive.moved
    assert set(drive.deleted) == {"content-1", "sidecar-1"}
