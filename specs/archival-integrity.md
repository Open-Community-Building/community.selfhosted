# Archival Integrity

## Purpose

State, as a binding behavioral boundary on every tool in this codebase and its
sibling packages (e.g. `community.mac_file_dump`), that an original/source
system is holdings to be preserved, not inventory to be optimized — deletion
of a file at an original/source location, and alteration of an artifact of
archival value, are out of scope for automated tooling, regardless of
redundancy, verified backups, or how carefully the mechanics of the operation
have been checked.

This spec is the missing complement to [Fixity & Change
Detection](fixity.md) and [Locations](locations.md). Those two describe what
this system *detects* — loss, redundancy, compliance state — and detection
stays exactly as valuable as it already is. This spec is about what tooling
is permitted to *do* about what it detects: report it to a human, always;
act on it autonomously, never, when the target is original data.

Adopted via [ADR-0001](../adr/0001-original-system-deletion-and-artifact-alteration-are-no-go.md),
which records the incident and reasoning that made this spec necessary.

## Definitions

- **Original/source location**: a location a project draws from as its live,
  authoritative record — a project's declared `primary_storage`, any location
  named in a project's `sources` (see [Locations](locations.md)), a mounted
  iOS device, an SD card being read directly, or any medium not explicitly
  and durably designated otherwise. In the current registry, most projects'
  `primary_storage` is exactly this; a few (e.g. a project scanning an
  already-established backup mirror) are not — see Constraints below on why
  that distinction is not currently trusted to gate anything automatically.
- **Derived/non-original location**: a location holding a copy made *from* an
  original, kept for redundancy or convenience, whose loss does not reduce
  the archive's actual holdings — a cache, scratch space, or a mirror
  explicitly and durably marked as such. No location in the current registry
  is treated as this for the purposes of this spec (see Constraints).
- **Archival artifact**: any file at an original/source location that is part
  of the personal archive this system exists to preserve — photos, videos,
  documents, exports, and anything else ingested rather than generated as a
  disposable intermediate (a thumbnail cache, a `.pyc` file, this system's
  own `fetch/`/`processed/` working directories are not archival artifacts).
- **Deletion**: removing an archival artifact from an original/source
  location by any means — `rm`, a generated shell script, a move to trash,
  a programmatic `os.remove`/`shutil.rmtree`/`Path.unlink`.
- **Alteration**: changing an archival artifact's content, location
  (path/filename), or encoding at an original/source location, other than
  as a recorded OAIS ingest or dissemination action (see
  [Dissemination](dissemination.md)) logged as a PREMIS-style event. Includes
  moving a file to "clean up" a folder structure, renaming to normalize a
  naming scheme, and re-encoding to save space — each of these can discard
  provenance (capture-date-bearing structure, acquisition-channel-bearing
  filenames) that the content alone doesn't carry, even though the bytes
  survive.
- **Disposal/appraisal workflow**: a distinct, deliberately out-of-scope
  future feature for retiring specific archival artifacts on purpose, with a
  documented rationale and a named responsible agent — not what this spec
  concerns itself with; see Behavior 4 and Open Questions.

## Behavior

1. No tool in this codebase may generate an executable script, or perform an
   action directly, whose effect is to delete an archival artifact at an
   original/source location. This holds regardless of how many
   verified-existing copies of the same content remain elsewhere, regardless
   of whether the content is byte-identical to another copy, and regardless
   of any correctness guard (existence check, staleness check, dry-run
   preview) applied to the deletion mechanism itself. A deletion being
   mechanically safe to execute is not the same claim as a deletion being
   archivally permitted, and only the second claim is in scope here.
2. No tool may move, rename, re-encode, or otherwise alter an archival
   artifact at an original/source location, except as an OAIS ingest or
   dissemination action recorded as a PREMIS-style event per
   [Locations](locations.md)' events ledger.
3. Detection and reporting of redundancy, duplication, size, and structure
   remain fully in scope and are explicitly encouraged — computing
   checksums, grouping by content hash, and surfacing what's duplicated
   (where, how much, of what kind) to a human is ordinary fixity/inventory
   work, exactly what [Fixity & Change Detection](fixity.md) already does for
   loss and what [Locations](locations.md)'s finding-aid view anticipates for
   redundancy. What's foreclosed by 1 and 2 is specifically turning that
   report into an executable path to delete or alter the original.
4. A future disposal/appraisal workflow — deliberately retiring a specific
   archival artifact, on purpose, with a documented rationale — is not
   forbidden by this spec, but is out of scope for it: any such workflow
   must be proposed as its own spec and reviewed under this project's
   existing SDD process *before* any code is written, and must itself model
   real institutional appraisal practice (a documented rationale per
   disposal decision, a named responsible agent, a retained record of what
   was removed and why, logged as an event *before* the removal occurs — not
   an extension of any existing detection command, which has none of that).

## Inputs

- A project's `config.json`: `primary_storage` / `sources` / `archive_targets`
  (see [Locations](locations.md)) — used only to determine what counts as an
  original/source location for the purposes of Behavior 1–2, never to
  determine that an operation is therefore safe.
- The command surface of every tool operating on project data, present and
  future, in `community.selfhosted` and its sibling packages.

## Outputs

- No positive output — this spec's effect is a permanent constraint. Its
  observable outcome is the *absence* of any tool capability that violates
  Behavior 1–2, checkable by reviewing a new or changed command's design
  against this spec before it ships (part of this project's existing SDD
  spec-review step), not by any runtime artifact.

## Constraints

- This spec applies regardless of what location is being targeted — it does
  not currently carve out an exception for a location a human believes is
  "just a mirror." The reason: this registry's own data shows the same
  field (`primary_storage`) plays both roles across different projects (one
  project's `primary_storage` is explicitly a live source; another's is
  explicitly a backup mirror it scans read-only) — a classifier meant to
  tell those apart automatically would itself be a single point of failure
  for this entire spec, and none exists today that this spec is willing to
  trust. If a durable, explicit, low-risk way to designate a location as
  genuinely non-original is ever built, it requires its own spec (and a
  superseding ADR) before any tool is allowed to act on that designation —
  it is not granted by this spec.
- This spec is `community.selfhosted`-specific and archival in nature; see
  `Sprezzatura`'s `specs/destructive-operations.md` (at
  `~/Writing/sprezzatura/specs/destructive-operations.md`) for the general
  software-engineering rule about irreversible operations on *any* system,
  which this spec supplements rather than replaces for archival data
  specifically — that spec's recoverability standard ("is there a backup")
  is necessary but not sufficient here: an archival artifact can be fully
  recoverable byte-for-bit and still be a no-go to delete or alter, because
  restoring bytes does not restore the fact that an independent copy once
  existed at a different path.
- See [ADR-0001](../adr/0001-original-system-deletion-and-artifact-alteration-are-no-go.md)
  for the specific incident and reasoning this spec formalizes, including
  what it means for tooling that predates this spec (e.g.
  `community.mac_file_dump`'s `dedup` command).

## Open Questions

- Should a durable "designated non-original" location marking ever be built
  (see Constraints), what would make it trustworthy enough to gate an
  automated action on — a human-entered, timestamped, hard-to-fat-finger
  declaration in `location.json` (parallel to `medium`'s closed enum), a
  minimum-copies-elsewhere check performed live rather than trusted from a
  stale registry, both?
- Should this spec's Behavior 1–2 also cover *non-file* alterations with
  similar archival stakes — e.g. stripping or rewriting EXIF/metadata during
  an import step, which is a form of alteration this spec's current
  definitions may not obviously reach?
- How should a new tool's author actually check their design against this
  spec before shipping — a checklist item in this project's own contribution
  process, or is "read this spec" sufficient given how few people work on
  this codebase today?
