# Source Manifest

## Purpose

Give every source a uniform, queryable **index of its items** — for each item a
stable *locator*, a content **checksum** (with its algorithm), and a few
*features* — so that sampling/test-sets, cross-source duplicate detection, dataset
statistics, fixity/change-detection, and parallel processing are written **once,
source-agnostically**, on top of a single artifact instead of being re-implemented
per source.

## Definitions

- **Source**: a dataset read item-by-item — a Google Takeout mbox, a Claude
  `conversations.json`, a photo folder, an iOS device over AFC.
- **Item**: the smallest addressable unit of a source — an email message, a
  conversation message, a file/photo, a device file. A source MAY also expose
  **sub-items** (e.g. an email's attachments) as items in their own right.
- **Locator**: a stable, cheap-to-seek address that re-identifies an item *within
  its source* and lets it be re-extracted without rescanning the whole source —
  e.g. an mbox byte offset, a filesystem path, an AFC device path, a
  `(conversation_uuid, position)` pair, a row id.
- **Checksum**: the message digest of an item's content bytes (e.g. MD5,
  SHA-256), recorded together with its **algorithm**. This is the item's *fixity*
  value — the basis for duplicate detection and for change detection over time
  (see [Fixity & Change Detection](fixity.md)). The naming follows digital-
  preservation convention (BagIt manifests, PREMIS `messageDigest`).
- **Features**: a small set of typed attributes describing where an item sits in
  the dataset's distribution — at minimum `kind`, `size`, `timestamp`; sources add
  their own (extension, mime, sender, language…).
- **Manifest**: a table with one row per item — `(seq, kind, locator, locator_kind,
  checksum, algorithm, size, features…)` — persisted as SQLite, indexing a source
  independently of any later conversion.
- **Item iterator**: the *only* per-source contract — it streams a source's items,
  yielding for each a `(locator, content, features)` triple. The generic manifest
  stage (and the converter) consume it.

## Behavior

### Indexing

1. A source supplies an **item iterator** that streams its items in a stable order,
   yielding for each: a `locator` unique within the source, the item's `content`
   (bytes, or a handle that produces them), and a `features` mapping.
2. The generic **manifest stage** consumes the iterator and, per item, computes the
   checksum over the content bytes, records the byte size, and appends a manifest
   row `(seq, kind, locator, locator_kind, checksum, algorithm, size, features…)`.
3. **Sub-items** (e.g. attachments) are emitted by the iterator as their own rows,
   carrying their parent's locator, so content is checksummed at the granularity
   cross-source dedup needs.
4. Indexing is **streaming and memory-bounded** — it never materialises the whole
   source (e.g. the gmail iterator yields one message at a time as it records
   `mbox_offset`; a photo iterator walks the tree one file at a time).
5. Indexing is **read-only** on the source; it writes only the manifest.

### One iterator, two consumers

1. Indexing and conversion share the **same item iterator**: converting = iterate
   items + write source-specific tables; indexing = iterate items + write the
   manifest.
2. A manifest MAY therefore be produced two ways: as a **standalone stage** (when
   you want the index *without* converting — e.g. to sample first), or as a
   **by-product of conversion** in a single pass. This is what keeps the universal
   index/checksum step from forcing a separate pre-pass onto every command.

### Locators

1. A locator MUST let an item be re-fetched on its own, cheaply, without rescanning
   the source (offset → seek; path → open; rowid → indexed lookup).
2. Indexing is **deterministic**: re-running over an unchanged source yields the
   same locators and checksums, so manifests are comparable over time and support
   incremental / resume and fixity checking.

### The manifest as the shared index

1. The manifest is stored as an **SQLite table**, so it is explorable in Datasette
   and usable for selection directly in SQL.
2. It is a **prerequisite artifact**: statistics, sampling, dedup, fixity and
   conversion all *read* it. It stores addresses + checksums + features only —
   never a copy of the source's content.

### Duplicate detection & fixity

1. Checksums are computed over **comparable units**, so the same bytes appearing in
   two sources (an email attachment and the same file in a photo set) share a
   checksum.
2. Duplicate detection is "group manifest rows by `checksum`" — within one manifest,
   or UNION-ed across many.
3. The same checksum, compared against a prior run's, is the **fixity** value used
   to detect silent content changes and losses across imports — see
   [Fixity & Change Detection](fixity.md).

### Hand-off to diversity & sampling

1. Each row carries enough features to characterise the dataset's distribution.
2. Aggregating those features produces the diversity profile that drives
   [Diversity Sampling](diversity-sampling.md) (separate spec): choose a subset of
   locators that covers the distribution, then re-extract just those items — via
   their locators — into a small test set that can live on a laptop while the full
   dataset stays on external storage.

## Inputs

- A source and its **item iterator**.
- Optionally, an existing manifest for the same source (incremental / resume).

## Outputs

- A **manifest** table for the source — rows of `(seq, kind, locator, locator_kind,
  checksum, algorithm, size, features…)` — in SQLite.

## Constraints

- Indexing is streaming, memory-bounded, read-only on the source, and deterministic.
- `checksum` = the message digest (hex) of the item's content bytes, using
  **SHA-256** (the digital-preservation default); the **`algorithm`** is recorded
  alongside (BagIt/PREMIS convention) so the digest stays interpretable and older
  MD5 ingests can coexist. `size` (bytes) is stored too.
- The **item iterator is the only per-source code**; the manifest, checksum and
  stats stages are generic across all sources.
- The manifest indexes a source without duplicating its content; downstream features
  consume the manifest, not the source.
- Locators are stable and cheap to seek; sampling's cost is bounded by the size of
  the selected subset, not of the source.

## Open Questions

- Where does the manifest table live — inside the source's own output database (a
  `manifest` table) or a standalone `<source>.manifest.db`? (Leaning: a `manifest`
  table in the source DB, so Datasette shows index and data together.)
- Heterogeneous locators (offset vs path vs tuple): store as one opaque `TEXT`
  column plus a `locator_kind`, or as typed columns? (Leaning: opaque `TEXT` +
  `locator_kind`, to keep one uniform schema across sources.)
- Define the **canonical content** for checksumming non-file items (e.g. an email
  message — raw RFC822 bytes? normalised?) per source.
- Should `kind` distinguish item vs sub-item explicitly (e.g. `message` vs
  `attachment`), and should sub-items reference the parent by `seq` or by locator?
- Where does the generic implementation live — the manifest/checksum/stats stages
  plus the **Source / item-iterator** contract — in **memex** (the source→SQLite
  package) or in **community.selfhosted** (which already hosts the photo/iOS
  pipelines this would absorb)? This spec is deliberately neutral on it.
- Promote the existing `photos_md5.py` / gmail `mbox_offset` / `ios_file_stat.py`
  behaviours into this one abstraction, or keep them as source-specific iterators
  that feed it?
