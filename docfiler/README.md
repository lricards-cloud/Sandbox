# docfiler — automatic paperwork filing

You take a photo of a receipt, medical form, warranty card, tax doc —
whatever needs filing — and add it to one Google Photos album. Everything
else happens automatically, landing as **two copies**: one filed in Google
Drive, one filed as a note in your Obsidian vault.

## How it works

```
 Google Photos album ──► Zapier: classify (AI) ──► Drive copy #1 (filed)
                                          │
                                          └──► "Hermes Inbox" handoff
                                                        │
                                                        ▼
                                          docfiler (this repo, runs
                                          alongside Hermes) polls the
                                          inbox and writes Obsidian
                                          copy #2: a markdown note with
                                          frontmatter + the attachment
```

- **Zapier** owns: watching the Photos album, AI classification (type,
  title, date, vendor, amount, tags, summary), and filing the permanent
  Google Drive copy into `Filing/<Category>/<Year>/`.
- **docfiler** owns: polling a Drive "Hermes Inbox" folder that Zapier
  drops a copy + JSON metadata sidecar into, and writing the second copy —
  a markdown note plus attachment — into your Obsidian vault at
  `<vault>/Filing/<Category>/<Year>/`.

See `docs/ZAPIER_SETUP.md` for the full Zap configuration and
`docs/METADATA_SCHEMA.md` for the sidecar contract between the two halves.

## Obsidian note format

```markdown
---
type: receipt
date: 2026-08-08
title: Home Depot - lumber and screws
vendor: Home Depot
amount: 42.17
currency: USD
tags: [receipt, home-improvement]
source: gdrive
drive_url: https://drive.google.com/file/d/.../view
status: filed
filed_at: 2026-08-08T10:32:00-06:00
---

# Home Depot - lumber and screws

![[2026-08-08_home-depot_lumber-and-screws.jpg]]

Receipt for lumber and screws for the deck repair.
```

One note per document, filed into dated folders per category
(`Filing/Receipts/2026/…`), with structured frontmatter so Dataview
queries and tag search both work.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .            # add ".[dev]" for tests
cp config.example.yaml docfiler.yaml
```

## Usage

```bash
docfiler check   # verify vault path + Drive inbox access
docfiler run     # file everything currently waiting, once
docfiler watch   # poll on a loop (config: poll.interval_sec)
```

All commands accept `--config PATH` (default `docfiler.yaml`) and `-v` for
debug logging.

## Configuration

Everything is in `docfiler.yaml` (copied from `config.example.yaml`):

- `drive.credentials_file` — service-account JSON key (see
  `docs/ZAPIER_SETUP.md` for setup + folder sharing).
- `drive.inbox_folder_id` / `drive.done_folder_id` — the "Hermes Inbox"
  handoff folder, and where processed pairs get moved (blank = delete).
- `obsidian.vault_path`, `filing_root`, `attachments_dirname` — where the
  Obsidian copy is written.
- `categories` — maps a document's classified `type` to a folder name;
  should match the folder names your Zap uses for the Drive copy.
- `poll.interval_sec`, `poll.state_file` — polling cadence and where
  processed Drive file IDs are tracked (dedup across restarts).

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests cover metadata parsing/validation, filename conventions, the
Obsidian note/attachment writer, and the poller's pairing/dedup/retry
logic — all offline against fakes, no Drive credentials or network
required.

```
docfiler/
  models.py         DocMetadata + validation
  metadata.py        parses the JSON sidecar
  naming.py          filename/slug conventions
  obsidian_filer.py  writes the vault note + attachment
  drive_client.py    thin Drive v3 wrapper (list/download/move/delete)
  poller.py          pairs inbox files, dedups, drives the filing loop
  config.py          YAML config + defaults
  cli.py             `docfiler run|watch|check`
docs/
  ZAPIER_SETUP.md     full Zap configuration
  METADATA_SCHEMA.md  the sidecar contract
tests/
```
