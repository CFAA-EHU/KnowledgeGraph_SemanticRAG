# Context

`data/processed` currently behaves like a flat namespace even though it contains several classes of artifacts with different operational meaning.

# Objective

Define the policy and registry for `data/processed` so runtime artifacts, accepted project artifacts, historical campaign outputs, and diagnostics are no longer treated as equivalent.

# Scope

- Generate `data/processed/t27_processed_artifact_policy.json`.
- Generate `data/processed/t27_processed_artifact_registry.json`.
- Classify artifacts into:
  - runtime contract
  - accepted project operational artifacts
  - historical campaign traceability
  - debug and diagnostics
- Mark which artifacts are rebuilt, preserved, non-contractual, or candidate for future archival.

# Non-goals / Later

- Do not physically move `data/processed` contents yet.
- Do not delete historical outputs.

# Constraints / Caveats

- The policy must match the current runtime behavior and rebuild intent.
- Historical T21-T27 artifacts must remain traceable but excluded from the runtime contract.
- The registry should be practical enough to inform later cleanup or archival decisions.

# Acceptance Notes

- The policy must remove ambiguity about what the rebuild is allowed to consume as authoritative input.
