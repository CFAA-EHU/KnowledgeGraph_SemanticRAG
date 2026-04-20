# Context

T27B must end with an honest decision on whether the repository is now structurally ready for reuse and for a later case-specific split.

# Objective

Validate the repository after T27B structural isolation work and generate the final T27 cleanup/decision state.

# Scope

- Run the approved non-regression checks after T27B changes.
- Update or generate the final reports needed to state:
  - whether historical tooling is isolated
  - whether the repository is ready for reuse
  - whether the repository is ready for a later case-specific split
- Refresh `data/processed/t27_repo_structure_refactor_report.json` if needed.
- Refresh:
  - `data/processed/t27_repo_cleanup_report.json`
  - `data/processed/t27_repo_cleanup_decision_report.json`

# Non-goals / Later

- Do not start the new case-specific repository.
- Do not introduce new runtime functionality.

# Constraints / Caveats

- If a baseline regresses, stop and report honestly.
- GraphDB health must remain green.
- The final decision must distinguish between “ready for reuse” and “ready for case-specific split” without overstating what T27B actually accomplished.

# Acceptance Notes

- This task closes T27 as an architectural cleanup effort only if the runtime remains healthy and the structural boundary is visibly improved.
