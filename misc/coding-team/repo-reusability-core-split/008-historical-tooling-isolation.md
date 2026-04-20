# Context

T27A already declassified historical tooling from the operational primary path. T27B now needs to isolate that tooling structurally or semantically with the lowest possible compatibility risk.

# Objective

Isolate historical campaign tooling so it is clearly outside the operational path while preserving traceability and avoiding runtime breakage.

# Scope

- Use the structural isolation candidate report as the source of truth.
- Apply only low-risk structural or semantic isolation to historical tooling, such as:
  - moving clearly non-operational wrappers into a historical grouping area
  - adding compatibility-preserving redirects or documentation stubs if needed
  - reclassifying legacy planning or campaign artifacts where movement is not yet safe
- Update any required references so operational docs and stable contracts remain correct.

# Non-goals / Later

- Do not move runtime-critical modules.
- Do not refactor imports broadly.
- Do not change runtime semantics.
- Do not isolate project-specific datasets yet beyond what is required for historical tooling clarity.

# Constraints / Caveats

- Historical tooling must remain discoverable for traceability.
- No historical script may continue to appear as a primary operational entrypoint after this task.
- Prefer minimal moves and compatibility-preserving shims over aggressive cleanup.

# Acceptance Notes

- After this task, the repo should make it visually and contractually obvious which tooling is historical.
