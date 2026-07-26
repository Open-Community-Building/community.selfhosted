# Architecture Decision Records

An append-only log of this project's significant technical/policy decisions —
complementary to `specs/`, not a replacement for it. A spec (see
[../README.md](../README.md#specs)) describes *what the system does*, kept
current as behavior evolves. An ADR records *why a boundary was drawn where
it was drawn*, especially one discovered through a real incident rather than
planned up front — and is never edited after the fact. A decision that
changes is recorded as a *new*, higher-numbered ADR that names the one it
supersedes; the original stays exactly as filed, wrong-in-hindsight parts
included, because the historical reasoning is the point.

## Convention

- One file per decision: `NNNN-title-in-kebab-case.md`, four-digit
  zero-padded, strictly monotonic. Numbers are never reused, including for a
  superseded or rejected decision.
- Template:

  ```
  # ADR-NNNN: Title

  ## Status
  Proposed | Accepted | Superseded by ADR-XXXX

  ## Context
  What situation, tension, or incident made this decision necessary --
  stated plainly enough that someone with none of the surrounding
  conversation could understand why this needed deciding.

  ## Decision
  The decision itself, stated as a rule, not a narrative.

  ## Consequences
  What this rule commits the system to going forward -- including costs,
  things it now forecloses, and any follow-up work the decision implies.
  ```

## Log

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-original-system-deletion-and-artifact-alteration-are-no-go.md) | Deletion of original/source-system files, and alteration of archival artifacts, are no-go | Accepted |
