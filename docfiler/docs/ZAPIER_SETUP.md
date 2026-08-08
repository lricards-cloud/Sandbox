# Zapier setup

This Zap is the front half of the pipeline: it watches a Google Photos
album, classifies each new item with AI, files the permanent copy in Google
Drive, and hands a copy + metadata sidecar to Hermes for filing into
Obsidian. `docfiler` (this repo) is the back half, running wherever Hermes
runs, polling the handoff folder.

```
 you add a photo/PDF        Zapier                              Hermes (docfiler)
 to the Photos album  ──►  1. classify (AI)                ┌──► filed copy stays in Drive
                       │   2. upload → Filing/<Cat>/<Year>/ │    (copy #1, done)
                       │   3. upload → Hermes Inbox/        │
                       └───────────────────────────────────┘
                                                              4. poll Hermes Inbox
                                                              5. write note + attachment
                                                                 into Obsidian vault
                                                                 (copy #2)
                                                              6. move inbox pair → done/
```

## 1. Drive folders to create first

In Google Drive, create:

- `Filing/` with a subfolder per category: `Receipts`, `Medical`, `Tax`,
  `Warranties`, `Legal`, `Insurance`, `Statements`, `Other` (must match the
  `categories` mapping in `config.example.yaml`). Year subfolders
  (`Filing/Receipts/2026/`) can be created on the fly by the Zap — see step 3.
- `Hermes Inbox/` — the handoff folder. Copy its folder ID (the string
  after `/folders/` in its URL) into `drive.inbox_folder_id` in your config.
- `Hermes Inbox/done/` (optional) — if set as `drive.done_folder_id`,
  processed pairs are moved here instead of deleted, so you have a paper
  trail.

## 2. Service account for docfiler

`docfiler` authenticates as a Google Cloud **service account**, not your
personal OAuth login (Zapier already has your personal OAuth for the
Photos/Drive steps below — no need to reuse it here):

1. In Google Cloud Console, create a service account and download its JSON
   key. Save it as `docfiler/service-account.json` (already gitignored).
2. Enable the Drive API on that project.
3. **Share** the `Hermes Inbox` folder (and its `done/` subfolder, if used)
   with the service account's email address (`...@...iam.gserviceaccount.com`),
   giving it Editor access. Without this share, `docfiler check` will fail.

## 3. The Zap

**Trigger** — Google Photos: *New Photo in Album*. Point it at the album
you add receipts/documents to.

**Step 2 — Classify (AI by Zapier or a Claude/OpenAI action)**

Prompt template:

```
You file personal paperwork. Given this image, return ONLY JSON matching
this shape (no prose, no markdown fences):

{
  "type": "receipt|medical|tax|warranty|legal|insurance|statement|other",
  "title": "short human title",
  "date": "YYYY-MM-DD (document's own date if legible, else today)",
  "vendor": "issuing store/provider/institution, or null",
  "amount": "total amount as a number, or null",
  "currency": "ISO code, default USD",
  "tags": ["1-3 extra topical tags"],
  "summary": "one or two sentence summary"
}
```

Map the output fields to named Zap variables (`type`, `title`, `date`,
`vendor`, `amount`, `currency`, `tags`, `summary`) for use in later steps —
most AI-by-Zapier actions let you define an output schema so each field is
individually referenceable rather than one JSON blob.

**Step 3 — Resolve the filed-copy folder (Google Drive: *Find a Folder*,
create if not found, run twice)**

1. Find/create folder named `{{type → category}}` inside `Filing/` — use a
   Zapier **Lookup Table** step right after classification to map `type` to
   the category folder name (`receipt` → `Receipts`, etc.), matching
   `config.example.yaml`'s `categories` block.
2. Find/create folder named `{{date | year}}` inside the category folder
   from step 3.1.

**Step 4 — Upload the filed copy (Google Drive: *Upload File*)**

- File: the original Photos item.
- Folder: the year folder from step 3.2.
- Filename: `{{date}}_{{vendor or type, slugified}}_{{title, slugified}}.{{ext}}`
  (a Zapier **Formatter → Text → Replace** or **Code** step can slugify —
  lowercase, spaces/punctuation → `-`).

**Step 5 — Upload the same file to the Hermes Inbox (Google Drive: *Upload
File*)**

- Same file, same filename as step 4.
- Folder: `Hermes Inbox`.

**Step 6 — Upload the metadata sidecar (Google Drive: *Upload File*, from
plain text)**

- Build the JSON body with a **Formatter → Text → Custom** or **Code** step
  from the classification output (see the schema in
  `docs/METADATA_SCHEMA.md`) — include `source_filename` from the original
  Photos item's filename.
- Upload as text/plain, same base filename as step 5 with a `.json`
  extension, into `Hermes Inbox`.

Steps 5 and 6 must land in the same run so the pair is complete by the time
`docfiler` next polls — if the Zap can fail partway, put a **Filter** or
error path after step 3 so a classification failure doesn't leave an
orphaned upload.

## 4. Running docfiler

```bash
cd docfiler
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.yaml docfiler.yaml   # fill in inbox_folder_id, vault_path, etc.
docfiler check                          # verify vault path + Drive access
docfiler run                            # process what's waiting, once
docfiler watch                          # poll on a loop (poll.interval_sec)
```

Point whatever supervises Hermes (cron, a systemd timer, a long-running
process) at `docfiler watch` (or `docfiler run` on a cron schedule) so new
photos get filed without you doing anything after adding them to the album.
