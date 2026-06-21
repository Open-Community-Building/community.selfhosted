# community.selfhosted

A photo inventory system for securing photos across multiple systems.

Built using **Spec Driven Development (SDD)** — specifications are written first, implementation follows from specs.

## What is SDD?

Spec Driven Development puts specifications at the center of the development workflow:

1. **Spec first** — Every feature begins as a specification describing *what* the system does, not *how*.
2. **Review the spec** — Specs are reviewed and agreed upon before any code is written.
3. **Implement from spec** — Code is written to satisfy the specification.
4. **Validate against spec** — Tests verify the implementation matches the spec.

Specs live in the `specs/` directory and are the source of truth for system behavior.

## Specs

| Spec                                               | Status  | Description                                              |
|----------------------------------------------------|---------|----------------------------------------------------------|
| [Configure Projects](specs/configure-projects.md)  | Draft   | Configure projects that have their own pipeline          |
| [Device Dump](specs/ios_file_stat.md)              | Draft   | Dump contents of devices, external storage and the cloud |
| [Photo Registry](specs/photo-registry.md)          | Draft   | Register Photos                                          |
| [MD5 Fingerprinting](specs/md5-fingerprinting)     | Draft   | Compute and store MD5 checksums for duplicate detection  |
| [Stats](specs/stats.md)                            | Draft   | Generate per-project and cross-project statistics        |


## Project Structure

```
community.selfhosted/
├── specs/              # Specifications (source of truth)
├── config.py           # Project configuration
├── photos_dump.py      # Dump photos from devices, external storage and cloud servers
├── photos_md5.py       # MD5 fingerprinting pipeline
├── photos_metadata.py  # MD5 fingerprinting pipeline
├── photos_md5.py       # MD5 fingerprinting pipeline
└── photos_stats.py     # Statistics generation
```

## Getting Started

Photo projects are stored under `~/selfhosted/photos/projects/`. Each project folder contains a `config.json` describing the source.

```bash
# List discovered projects
python config.py

# Compute MD5 checksums for all projects
python photos_md5.py

# Generate statistics
python photos_stats.py
```
