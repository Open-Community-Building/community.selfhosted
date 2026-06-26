# Fixity & Change Detection

## Purpose

Catch what silently changes between successive **ingests** of a source —
additions, losses, and above all *unannounced content changes* — by comparing
**checksums** over time. This is **fixity checking** in the digital-preservation
sense (OAIS Preservation Description Information "Fixity"; PREMIS fixity events;
BagIt manifests): the [Source Manifest](source-manifest.md)'s checksum is the
fixity value, and comparing it across ingests surfaces bit-rot, silent re-encodes,
and dropped entries that a plain re-import would otherwise hide.

## Definitions

- **Ingest**: one run that reads a source and records (appends) its manifest — the
  OAIS *ingest* process. Each ingest is identified and timestamped.
- **Fixity**: the property of an item's content being unchanged, verified by
  comparing its current **checksum** against the one a prior ingest recorded.
- **Fixity check**: comparing a new ingest's manifest against the previous ingest
  of the same source and classifying each item.
- **Fixity event**: the recorded outcome for an item across two ingests — one of
  *added*, *unchanged*, *metadata change*, *fixity failure*, *dropped*, *loss*.
- **Fixity failure**: same locator, *different* checksum — the content changed
  (the bit-rot / silent re-encode signal).
- **Loss**: a checksum present in a prior ingest that appears under *no* locator in
  the new one — content that is simply gone (vs a **move**, where the same checksum
  reappears under a different locator).

## Behavior

### Ingest history (append-only)

1. The manifest is **not overwritten**. Each ingest appends its items tagged with
   an `ingest_id`; an `ingests` table records `(id, source, run_at, algorithm,
   item_count)`.
2. This replaces the current `recreate=True` rebuild in `manifest.build` (see
   Constraints) — without retained history there is nothing to compare against.

### Fixity check

Compare ingest *N* against the previous ingest of the same source, keyed by
**locator** and cross-checked by **checksum**:

1. **added** — locator in *N*, absent before.
2. **unchanged** — locator in both, same checksum (and algorithm).
3. **metadata change** — same locator + checksum, different features (e.g. mtime, size).
4. **fixity failure** — same locator, *different* checksum → content changed.
5. **dropped** — locator present before, absent in *N*.
6. For each dropped locator, resolve **loss vs move** by checksum: if the checksum
   reappears under another locator in *N* it is a **move/rename**; if it appears
   nowhere it is a **loss**.

### Two lenses

- by **locator** — *did this address's content change?* (added / metadata change /
  fixity failure / dropped)
- by **checksum** — *did this content disappear or move?* (loss vs move)

### Change report (the alert)

1. Every ingest ends with a report: counts per class, and the full list of the
   **fixity failures** and **losses** for review. These must be surfaced — never
   silently swallowed.
2. Optionally persist each outcome as a row in a `fixity_events` table
   `(ingest_id, locator, class, old_checksum, new_checksum)` — an audit trail
   queryable in Datasette.

## Inputs

- Two ingests of the same source in the manifest (the current run and the previous),
  whose checksums were computed with the same **algorithm**.

## Outputs

- An `ingests` table and an `ingest_id` column on `items`; optionally a
  `fixity_events` table.
- A change report: per-class counts plus the full list of fixity failures and losses.

## Constraints

- **Append-only**: ingests are never overwritten — history must stay comparable over
  time (the whole point). `manifest.build` drops `recreate=True` for this.
- Checksums are only comparable within the same **algorithm**; the algorithm is
  recorded per item/ingest.
- A fixity failure or a loss is always reported, never hidden.
- Detection is heuristic about *intent*: an expected edit and silent corruption look
  identical by checksum — the report surfaces both and a human triages.

## Open Questions

- Retention: keep every ingest's full item set, or compact to (latest snapshot +
  `fixity_events` log)?
- Cross-source safety: a checksum gone from source A but present in source B is not a
  true loss — should the report consult other sources' manifests before crying loss?
- Should **move** detection also require matching features (not just an equal
  checksum), to avoid coincidental collisions?
- Algorithm migration (MD5 → SHA-256): how to re-checksum retained history without
  losing comparability across ingests?
