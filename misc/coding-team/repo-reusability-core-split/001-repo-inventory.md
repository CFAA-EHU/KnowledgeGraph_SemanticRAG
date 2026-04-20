# Context

The repository mixes reusable runtime code, accepted project assets, historical campaign outputs, and diagnostic artifacts. T27A starts by making that landscape explicit.

# Objective

Produce a repository inventory that classifies relevant files and directories by reusable/core status, project specificity, runtime criticality, and recommended handling.

# Scope

- Inspect root-level entrypoints, `src/`, `docs/`, `data/processed`, `data/golden_set`, and root utilities.
- Generate `data/processed/t27_repo_reusability_inventory.json`.
- Classify each relevant element with:
  - `path`
  - `type`
  - `category`
  - `runtime_critical`
  - `reusable`
  - `project_specific`
  - `recommended_action`
  - `notes`

# Non-goals / Later

- Do not move files.
- Do not change runtime behavior.
- Do not rewrite documentation yet.

# Constraints / Caveats

- Categories must be limited to the approved T27 vocabulary.
- The inventory must distinguish between runtime contract artifacts and accepted project artifacts.
- Historical reports and debug outputs must remain visible, but not be treated as runtime inputs.

# Acceptance Notes

- The inventory should be complete enough to support the later policy and contract tasks without ad hoc rediscovery.
