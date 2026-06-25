# Configure Projects

## Purpose

Provide a single, declarative configuration entry point for the toolkit, so the
projects root and the discovery strategy are *declared* rather than hard-coded,
and so each project can carry its own pipeline configuration. Configuration is
expressed and resolved using spaCy's config system (`confection`, exposed as
`spacy.registry`) — the same machinery as a spaCy training `config.cfg` — which
replaces the hand-written `config.py` while preserving the project registry that
[Photo Discovery](photo-registry.md) defines.

## Definitions

- **Config file** (`config.cfg`): A `confection`/spaCy config, at the repo root,
  declaring paths and which discovery component to use.
- **Registry function**: A Python function registered under `@spacy.registry.misc`
  that builds the project registry when the config is resolved.
- **Project registry**: The dictionary of projects keyed by `id`, with the
  computed paths defined in [Photo Discovery](photo-registry.md).
- **Resolved config**: The object graph returned by `spacy.registry.resolve()`,
  in which each registry-backed section is replaced by the value its function
  returns.

## Behavior

### Config File

1. Configuration lives in a `config.cfg` at the repo root.
2. A `[paths]` section declares `root`, the projects directory
   (default: `~/selfhosted/photos/projects/`).
3. A `[projects]` section selects a discovery function by name and passes it the
   root, e.g.:

   ```ini
   [paths]
   root = "~/selfhosted/photos/projects"

   [projects]
   @misc = "photo_projects.discover.v1"
   root = ${paths.root}
   ```

### Resolution

1. Load the config from disk: `Config().from_disk("config.cfg")`.
2. Resolve it with `spacy.registry.resolve(config)`, which invokes the named
   discovery function with the declared arguments.
3. The discovery function performs [Photo Discovery](photo-registry.md) and
   returns the project registry.
4. Each script obtains the registry by calling `load_projects()` from
   `project_registry` (`from project_registry import load_projects`); there is no
   module-level `config.py` singleton.

### Overrides

1. Any declared value may be overridden at load time without changing code — for
   example pointing at a different `paths.root` (a backup volume) by merging an
   override into the loaded config, mirroring how `spacy train` accepts
   `--paths.train` overrides.
2. Swapping the discovery *strategy* (e.g. reading a manifest instead of walking
   the filesystem) is a config edit — register a `photo_projects.discover.v2` and
   name it in `config.cfg`; call sites do not change.

### Per-Project Pipeline

1. Each project's `config.json` declares a `source` (e.g. `IPhone`, `IPad`,
   `Prompts`) that identifies which pipeline applies to it.
2. A stage skips projects whose `source` it does not handle, so a single command
   run over the registry only processes the relevant projects.

## Inputs

- A `config.cfg` at the repo root.
- A `config.json` in each project folder (see [Photo Discovery](photo-registry.md)).

## Outputs

- A resolved **project registry**: a dictionary keyed by project `id`, each entry
  carrying the project's configuration plus the computed paths from
  [Photo Discovery](photo-registry.md). This is the same shape callers consume
  today via `from config import photo_projects`.

## Constraints

- Configuration is parsed and resolved with spaCy's config system (`confection`);
  there is no bespoke config parser.
- Discovery logic is a registered function, swappable via `config.cfg` without
  touching call sites.
- Resolution is **side-effect free**: building the registry must not create
  directories. Creating each project's `fetched/` and `processed/` folders is the
  explicit `ensure-dirs` command (`project_registry.ensure_dirs`), not a side
  effect of import/resolution as the previous `config.py` did.
- The resolved registry preserves the keys defined in
  [Photo Discovery](photo-registry.md) so existing stages keep working.

## Open Questions

- Should a project declare its pipeline explicitly in `config.json`
  (e.g. `"pipeline": ["md5", "metadata", "stats"]`) instead of stages inferring
  applicability from `source`?
- Where should `config.cfg` live, and should its values be overridable from the
  `project.yml` `vars` / environment so the weasel commands and the library share
  one source of truth?
- Should `config.cfg` support multiple roots or remote/cloud sources in one run?
