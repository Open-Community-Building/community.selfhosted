# ADR-0001: Deletion of Original/Source-System Files, and Alteration of Archival Artifacts, Are No-Go

## Status

Accepted

## Context

`community.mac_file_dump`'s `dedup` command was built, extended, and
incrementally hardened over a single working session on 2026-07-25: first to
report duplicate files by content hash, then to emit absolute paths for a
deletion reference, then to become a directly executable `/bin/sh` script
(`duplicate-paths.sh`) that `rm`s every copy but one in each duplicate group.
Four safety guards were added reactively, each following a real near-miss
discovered mid-session, not designed in up front:

1. `protected_paths` -- added after the script was found to contain 32,156
   `rm` lines (of 32,157 total) pointing inside `Photos Library.photoslibrary`,
   Photos.app's own internal package.
2. A runtime `[ -e "$1" ]` existence guard (`rmv()`) -- added after a real
   stale checksum was found: a file the script targeted for deletion no
   longer existed, because `files-checksums.ndjson` was 2.3 days older than
   a fresher `list` run, and would have aborted the entire script under
   `set -e`.
3. A staleness warning comparing checksum age against a fresher file listing
   -- added alongside (2), advisory only.
4. A fix verifying that each duplicate group's *survivor* -- the copy every
   other path is `rm`'d against -- is itself confirmed to still exist, after
   it was noticed, in review, that a stale "kept" record could anchor
   deletion of every other real remaining copy in a group, leaving zero
   copies of that content behind.

Each of these four guards is sound engineering and each addresses a real
bug. But every one of them addresses the same class of question: does the
generated `rm` succeed correctly against the true state of the filesystem.
None of them addresses a different, prior question that was never asked
during this session: should this codebase ever generate an executable
script whose purpose is to delete copies of files from a project's
`primary_storage` -- its original, archival source -- at all.

`community.selfhosted`'s own founding README and specs (`fixity.md`,
`locations.md`) commit this system to OAIS-style ingest, PREMIS-aligned
provenance events, BagIt-shaped fixity, and 3-2-1-1-0 redundancy compliance
-- a posture in which redundancy is the asset being verified and grown,
never the waste being cleared, and in which loss of any kind is a reportable
event requiring human triage, never a silent or autonomous outcome. `dedup`'s
`rm`-script generation, run against a project's `primary_storage`, is in
direct tension with that posture: content-identical (same SHA-256) is a
claim about bytes, not a claim that two copies are interchangeable or that
one is disposable -- independent storage paths, filenames, directory
structure, and which app or sync client produced a given copy are themselves
provenance information this codebase's own tooling (`gallery`, `by-year`)
already relies on elsewhere, and that information does not survive a
same-hash `rm`.

Separately, `find_duplicates.py`'s own module docstring cites
`specs/destructive-operations.md` as the document governing its read-only
claim. No such file exists anywhere under `community.mac_file_dump`; no
spec review of this command's destructive capability occurred before it
shipped. That citation to a nonexistent governing document, sitting in code
that generates deletion scripts against original data, is itself evidence
of the risk this ADR exists to close off: tooling that speaks in the
register of spec-governed safety without the review having actually
happened.

## Decision

1. Deletion of any file on a source/original system -- a project's declared
   `primary_storage`, any location serving as a project's active source per
   `community.selfhosted`'s `locations.md` registry, or any medium not
   explicitly and durably designated as a non-original derived copy -- is a
   no-go. No tool in this codebase may generate an executable script, or
   perform an action directly, whose effect is to remove such a file. This
   holds regardless of how many verified-existing copies of the same content
   remain elsewhere, regardless of whether the content is byte-identical to
   another copy, and regardless of any staleness or existence guard applied
   to the deletion mechanism itself -- mechanical correctness of a delete
   operation is not a justification for the delete operation existing.

2. Alteration of an artifact of archival value -- moving, renaming,
   re-encoding, or otherwise modifying an original file's content, location,
   or filename in a way that isn't itself an OAIS ingest/dissemination
   action recorded as a PREMIS-style event -- is likewise a no-go, for the
   same reason: an artifact's structure, path, and filename can carry
   provenance information (capture date, acquisition channel, custodial
   history) that content hashing alone discards, and that information cannot
   be reconstructed once altered, no matter how many byte-identical backups
   survive.

3. Detection and reporting of redundancy remains fully in scope and is
   explicitly encouraged. Tools may compute checksums, group by content
   hash, and report duplication, size, and structure to a human -- this is
   ordinary fixity/inventory work consistent with `fixity.md` and produces
   the finding aids `locations.md` already anticipates. What is foreclosed
   is specifically the generation of an executable path from that report to
   a deletion, against original data.

4. This supersedes whatever implicit assumption allowed
   `community.mac_file_dump`'s `dedup` command to generate
   `duplicate-paths.sh` against a project's `primary_storage`. Retiring that
   code path itself is tracked as follow-up work, not performed by this ADR
   directly -- this ADR records the decision and its binding force; the
   corresponding code change is implemented separately and referenced here
   once done. `dedup`'s detection and reporting outputs (`duplicates.ndjson`,
   `duplicates-summary.json`, `empty-files.txt`, the `protected_paths`
   taxonomy) are retained unchanged -- none of that work is invalidated by
   this decision; only the script-writing half of the command is affected.

5. Any future disposal/appraisal workflow, if one is ever wanted, is out of
   scope for this ADR and must be proposed as its own spec, reviewed under
   this codebase's existing Spec Driven Development process before any code
   is written, explicitly modeling institutional appraisal practice (a
   documented rationale per disposal decision, a named responsible agent, a
   retained record of what was removed and why, logged as an event before
   the removal occurs) -- not extended from the current `dedup` architecture,
   which has no per-item rationale, no named agent, and no event log.

## Consequences

- Formalized as [Archival Integrity](../specs/archival-integrity.md), a new
  `community.selfhosted` spec stating this rule in the project's existing
  Purpose/Definitions/Behavior/Inputs/Outputs/Constraints/Open-Questions
  form, for the same audience `fixity.md` and `locations.md` already serve.
- `Sprezzatura`'s `specs/destructive-operations.md` is amended with a
  cross-reference: operations touching a `community.selfhosted`-registered
  project are additionally governed by the Archival Integrity spec, and
  recoverability (Sprezzatura's own standard) is necessary but not
  sufficient for such operations.
- `mac-file-dump dedup` writing `duplicate-paths.sh` is now in violation of
  this ADR and the Archival Integrity spec it produced. Retiring that code
  path is open follow-up work, not yet done as of this ADR's acceptance --
  tracked separately, not silently assumed complete by this record existing.
- No command in `community.mac_file_dump` or `community.selfhosted` may be
  extended in the future to delete, move, or alter files at a project's
  `primary_storage` or any registered source location, without a prior ADR
  explicitly superseding this one and a spec reviewed under SDD before code
  is written.
- Space reclamation is permanently out of scope as a goal for this codebase
  when applied to original/source locations. It remains a legitimate
  operator concern for derived, non-original storage (caches, scratch
  space, disposable mirrors explicitly marked as such) but no automated
  tooling in this codebase currently distinguishes those cleanly enough to
  be trusted with generating executable deletions even there; that
  distinction, if ever built, requires its own spec and is not granted by
  this ADR.
- Existing `fetch/duplicate-paths.sh` files already on disk for
  `macbook_maik_photos` and `macbook_maik_googledrive` are not retroactively
  deleted by this ADR (that would itself be an alteration to be treated with
  the same caution); they remain as an artifact of the pre-ADR design and
  should not be executed. Whether to remove them by hand is an operator
  decision outside this ADR's scope.
