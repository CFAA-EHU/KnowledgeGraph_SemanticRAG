# Context

The repository currently exposes both stable operational entrypoints and campaign-specific wrappers. T27A needs a clean operational contract.

# Objective

Define the stable operational entrypoint contract and the historical tooling registry.

# Scope

- Generate `data/processed/t27_stable_entrypoint_contract.json`.
- Generate `data/processed/t27_historical_tooling_registry.json`.
- Identify the official paths for:
  - runtime rebuild
  - GraphDB publish
  - GraphDB healthcheck
  - evaluation
- Identify historical wrappers and utility scripts that must remain traceable but non-primary.

# Non-goals / Later

- Do not remove historical scripts.
- Do not move scripts yet unless absolutely required for classification.

# Constraints / Caveats

- `run_t25*`, `run_t26*`, recovery wrappers, and diagnostics must not remain documented as normal operational rebuild paths.
- The contract should reflect the currently intended stable rebuild path, not every path that happens to work.
- Keep compatibility with the current runtime and rebuild workflow.

# Acceptance Notes

- The resulting contract should let docs point to one operational rebuild path only.
