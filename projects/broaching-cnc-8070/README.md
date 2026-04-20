# Broaching CNC 8070 Reference Project

This directory is the canonical grouping area for the retained broaching/CNC 8070 reference scope that still lives inside the reusable core repository.

It exists to make the project-specific boundary explicit while keeping the current runtime rebuildable from the existing paths.

Use this area to understand what belongs to the reference project:

- accepted source manuals under `data/raw/`
- golden sets and current project gates under `data/golden_set/`
- shared project-derived cache in `cache/terms_cache.json`
- accepted manual-specific processed artifacts in `data/processed/a218_*`, `quick_ref_*`, `installation_manual_*`, `8070_installation_*`, and `man_8070_err_*`
- project-tuned retrieval modules in `src/8_retrieval/`

Canonical manifest:

- `project_scope_manifest.json`

Compatibility notes:

- The live files above remain in their original locations for rebuild and validation compatibility.
- This grouping area is the canonical place to document the future split target for the broaching-specific repository.
