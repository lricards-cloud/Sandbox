from docfiler.models import DocMetadata
from docfiler.obsidian_filer import ObsidianFiler


def _filer(vault_path):
    return ObsidianFiler(vault_path=str(vault_path))


def test_files_attachment_and_note_in_dated_category_folder(tmp_path):
    filer = _filer(tmp_path)
    meta = DocMetadata(
        type="receipt", title="Lumber and screws", date="2026-08-08",
        vendor="Home Depot", amount=42.17, tags=["home-improvement"],
        summary="Receipt for lumber.",
    )

    filed = filer.file(meta, b"fake-bytes", "jpg", drive_url="https://drive.example/abc")

    expected_dir = tmp_path / "Filing" / "Receipts" / "2026"
    assert filed.note_path == expected_dir / "2026-08-08_home-depot_lumber-and-screws.md"
    assert filed.attachment_path == expected_dir / "_attachments" / "2026-08-08_home-depot_lumber-and-screws.jpg"
    assert filed.attachment_path.read_bytes() == b"fake-bytes"

    note = filed.note_path.read_text()
    assert "type: receipt" in note
    assert "vendor: Home Depot" in note
    assert "amount: 42.17" in note
    assert "drive_url: https://drive.example/abc" in note
    assert "status: filed" in note
    assert "# Lumber and screws" in note
    assert "![[2026-08-08_home-depot_lumber-and-screws.jpg]]" in note
    assert "Receipt for lumber." in note


def test_unknown_category_falls_back_to_other_folder(tmp_path):
    filer = ObsidianFiler(vault_path=str(tmp_path), categories={"other": "Other"})
    meta = DocMetadata(type="receipt", title="Mystery doc", date="2026-01-01")

    filed = filer.file(meta, b"x", "pdf")

    assert filed.note_path.parent == tmp_path / "Filing" / "Other" / "2026"


def test_omits_amount_and_currency_when_not_a_receipt(tmp_path):
    filer = _filer(tmp_path)
    meta = DocMetadata(type="medical", title="Annual checkup", date="2026-03-01")

    filed = filer.file(meta, b"x", "pdf")

    note = filed.note_path.read_text()
    assert "amount:" not in note
    assert "currency:" not in note
