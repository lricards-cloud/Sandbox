# Metadata sidecar contract

For every document Zapier files, it drops **two files** into the "Hermes
Inbox" Drive folder, sharing the same base filename:

```
2026-08-08_home-depot-receipt.jpg    <- the document itself
2026-08-08_home-depot-receipt.json   <- this sidecar
```

`docfiler` only processes a pair once both files are present, so the two
Zapier upload steps don't need to be atomic.

## Fields

| Field             | Required | Type                | Notes |
|-------------------|----------|---------------------|-------|
| `type`            | yes      | string (enum)       | One of `receipt`, `medical`, `tax`, `warranty`, `legal`, `insurance`, `statement`, `other`. Anything else is coerced to `other`. |
| `title`           | yes      | string              | Short human title, e.g. "Home Depot — lumber and screws". |
| `date`            | yes      | string (`YYYY-MM-DD`) | The document's own date if legible, otherwise the date it was captured. |
| `vendor`          | no       | string              | Who issued the document (store, provider, institution). |
| `amount`          | no       | number              | Total amount, if a receipt/invoice/statement. |
| `currency`        | no       | string              | ISO code, defaults to `USD`. |
| `tags`            | no       | array of strings    | Extra tags beyond `type` (which is always added as a tag). |
| `summary`         | no       | string              | One or two sentence AI summary, appended to the Obsidian note body. |
| `source_filename` | no       | string              | Original filename from Google Photos, for traceability. |

## Example

```json
{
  "type": "receipt",
  "title": "Home Depot - lumber and screws",
  "date": "2026-08-08",
  "vendor": "Home Depot",
  "amount": 42.17,
  "currency": "USD",
  "tags": ["home-improvement"],
  "summary": "Receipt for lumber and screws for the deck repair.",
  "source_filename": "IMG_20260808_101532.jpg"
}
```

## Validation

`docfiler.metadata.parse_metadata` / `DocMetadata.from_dict`
(`docfiler/models.py`) enforces:

- `type`, `title`, `date` must be present and non-empty.
- `date` must match `YYYY-MM-DD` (raises otherwise — the pair is left in
  the inbox and retried next poll after you fix the Zap).
- `type` outside the enum silently falls back to `other` rather than
  failing, since misclassification shouldn't block filing.
- `amount`, when present, is coerced to `float`.
