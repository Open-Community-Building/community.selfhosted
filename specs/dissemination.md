# Dissemination (Audience DIPs)

## Purpose

Make the archive's data available to five distinct **audiences** —
**self / family / friends / project / public** — by building, for each audience, a
filtered **DIP** (Dissemination Information Package, OAIS) of exactly what they're
allowed to see, and delivering each DIP to a **Hetzner Storage Box subaccount**
scoped to that audience.

The master AIP is the unfiltered source of truth; DIPs are derived and refreshed
periodically. This is the OAIS *Access* / dissemination leg, mirroring the OAIS
*Ingest* leg that the manifest pipeline already implements.

## Definitions

- **AIP** (Archival Information Package): the unfiltered master archive — the
  union of `~/selfhosted/archive/archive.sqlite`, the per-project derived databases
  (`manifest.sqlite`, `conversations.sqlite`, `gmail.sqlite`, `git.sqlite`), and
  the raw items they index. Never disseminated as-is.
- **Audience**: one of five concentric access levels, each viewing its own + every
  more public tier:
  - **`self`** — Maik, full access
  - **`family`**
  - **`friends`**
  - **`project`** — each project is its own collaboration audience, scoped to that
    project's rows only
  - **`public`** — the `community.selfhosted` / `community.memex` GitHub repos and
    a public Datasette
- **DIP** (Dissemination Information Package): a per-audience package — a
  filtered SQLite database (or several), a finding aid, all bundled as a **BagIt
  bag** (RFC 8493) so the audience can verify integrity end-to-end with standard
  tools.
- **Subaccount target**: a Hetzner Storage Box subaccount, scoped to a directory,
  holding one audience's DIP. The Storage Box exposes SFTP, WebDAV, BorgBackup
  and others; the protocol used here is **SFTP** (per [[feedback-recommend-sensible-choices]]).

## Behavior

### Access policy

1. Every entity in the archive (location, project, item, event, derived row)
   carries an `access_tier`: the **lowest** audience permitted to see it.
2. The policy is **`viewer_tier ≥ entity_tier`** in the tier ordering
   `self > family > friends > project > public`. A `family` viewer sees
   everything tagged `family`, `friends`, or `public`; a `public` viewer sees
   only `public`.
3. `project`-tier rows are additionally scoped to a specific project_id; a viewer
   with access to project P sees its `project`-tier rows plus everything more
   public, but not the project-tier rows of project Q.

### DIP build

1. For each target audience, `build_dip(tier)` materialises a SQLite database
   (`archive.<tier>.sqlite`) by selecting every table in the master archive
   filtered to rows whose `access_tier` ≥ the target tier (and, for `project`,
   matching the audience's project_id).
2. The build also copies any per-project derived databases the target tier is
   allowed to see (e.g. the photos `manifest.sqlite` for `family`, or the public
   `git.sqlite` for `public`) — each itself filtered if it carries per-row
   `access_tier`.
3. A **finding aid** (`finding_aid.md`, generated from the master archive) heads
   the bag: what's in this package, who built it, when, which projects /
   locations contributed, how to verify. The human-readable counterpart to the
   SQLite metadata.
4. The package is assembled as a **BagIt bag** with a `manifest-sha256.txt` and
   `bag-info.txt` — the audience can verify it end-to-end with `bagit-python`,
   `bagit-cli`, or any other standard implementation.

### Delivery to Hetzner Storage Box

1. Each audience has a **subaccount** on the Hetzner Storage Box, scoped to that
   audience's directory, with its own SSH key (private key stored at self tier
   only).
2. Delivery is `rsync -e ssh` (or plain `sftp`) of the bag's directory to the
   subaccount's home — incremental, so unchanged bytes don't re-transfer.
3. Delivery is **append-only on the audience side**: a new bag is uploaded to a
   timestamped directory `archive-YYYY-MM-DD/` and only after the upload completes
   does a `current` symlink swing to it. The audience always has the most recent
   intact view, even mid-upload.
4. Each successful delivery writes a `disseminated` event to the master events
   ledger: `(when, tier, subaccount, bag_sha256, byte_count)`. Dissemination has
   the same provenance trail as ingest.

### Relationship to 3-2-1-1-0

1. A self-tier subaccount on the Storage Box may *also* hold an encrypted bag of
   the full AIP — making the Storage Box the **off-site** copy in the per-project
   3-2-1-1-0 evaluation ([Locations](locations.md)).
2. Storage Box is **online** (SFTP-reachable); it satisfies **off-site** but not
   the **offline / immutable** leg. At least one truly offline copy is still
   required somewhere (a USB drive in a drawer, an optical disc, or a Storage
   Box snapshot held immutably — see Open Questions).

## Inputs

- The master `~/selfhosted/archive/archive.sqlite` and the per-project derived databases.
- An `audiences.json` per Storage Box: `{tier, host, subaccount, remote_dir,
  ssh_key_path, project_id?}`. Kept outside the public repo.
- The `access_tier` column on every disseminated entity.

## Outputs

- One `archive-<date>/` BagIt bag per audience, containing
  `archive.<tier>.sqlite`, the per-tier derived databases, and `finding_aid.md`.
- A `current` symlink pointing at the latest successful bag on the subaccount.
- A `disseminated` event per upload in the master events ledger.

## Constraints

- DIPs are **derived**; they are never the source of truth. A bad DIP is fixed
  by rebuilding from the AIP, not by editing the DIP.
- Package format is **BagIt** (RFC 8493) with SHA-256 manifests, so the audience
  can verify integrity end-to-end with standard tools.
- Transport is **SFTP** to Hetzner Storage Box subaccounts (per
  [[feedback-recommend-sensible-choices]]); WebDAV is not used.
- The **public**-tier DIP MUST match what is already in the `community.selfhosted`
  / `community.memex` GitHub repos — the leak audits Maik runs against those
  repos are the same compliance check for the public tier, by another name.
- Subaccount credentials and `audiences.json` are private; only the build
  scripts at self tier carry them.

## Open Questions

- **Encryption at rest** on the Storage Box: per-audience `age` (or `gpg`)
  encryption of the bag, or trust subaccount isolation? Subaccount isolation
  alone leaks ciphertext to Hetzner staff in principle; `age` over the bag is
  cheap and rules that out.
- **Immutability**: Hetzner Storage Boxes offer snapshots and "Immutable
  Backups" — does a snapshot held read-only count as the **1 immutable** leg of
  3-2-1-1-0, or does the strategy still require a separate offline medium?
  (PREMIS-strict would say the latter — different failure modes.)
- **Refresh cadence**: on-demand only, daily cron, or after every ingest?
  Incremental rsync makes "after every ingest" cheap.
- **Project-tier audience members**: per-project field in `config.json` listing
  authorised subaccounts, or a separate `audiences.json` keyed by project?
- **Audience-facing UX**: just the bag + a README, or a static-rendered Datasette
  snapshot in the bag so the audience can browse without installing anything?
- **Retention**: how many timestamped bags does each subaccount keep before the
  oldest is pruned? Storage Box has fixed capacity; "keep all" is not free.
