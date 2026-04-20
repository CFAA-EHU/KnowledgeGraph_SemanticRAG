# Project Groupings

This area makes retained project-specific scopes visible without moving live runtime paths that the current rebuild still depends on.

The reusable core remains rooted in the main repository paths and operational entrypoints. Project groupings here are canonical boundary markers for future extraction into dedicated repositories.

Current grouping:

- `broaching-cnc-8070/`: retained reference project for the accepted broaching and CNC 8070 manual corpus, golden sets, project-tuned retrieval modules, and accepted manual-level processed artifacts.

Compatibility notes:

- Live project inputs still remain in `data/raw/`, `data/golden_set/`, `cache/terms_cache.json`, and accepted manual-specific `data/processed/*` paths.
- Groupings here are documentary and contractual. They do not replace the current live operational paths.
