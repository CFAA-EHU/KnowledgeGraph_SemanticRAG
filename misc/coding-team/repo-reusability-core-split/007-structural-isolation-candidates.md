# Context

T27A defined the contractual boundary between reusable core, project-specific assets, historical tooling, and processed artifact classes. T27B starts by identifying what can be isolated structurally without putting the runtime at risk.

# Objective

Produce a low-risk structural isolation plan that identifies which paths can be reclassified, grouped, or moved with minimal compatibility risk, and which paths must remain in place for now.

# Scope

- Inspect the T27A inventory, policy, entrypoint contract, processed artifact policy, and documentation outputs.
- Identify low-risk candidates for:
  - historical tooling isolation
  - project-specific asset encapsulation
  - future archival grouping
- Generate `data/processed/t27_repo_structure_refactor_report.json`.

# Non-goals / Later

- Do not move files in this task.
- Do not change imports.
- Do not alter runtime behavior.
- Do not start the actual case-specific split.

# Constraints / Caveats

- Prefer semantic isolation over physical movement when movement would force broad path or import changes.
- Explicitly call out paths that are too risky to move during T27B.
- The report must be actionable enough to drive the next two T27B tasks.

# Acceptance Notes

- The output should distinguish:
  - safe-to-isolate-now
  - keep-in-place-but-reclassify
  - defer-to-future-project-repo
  - archive-later
