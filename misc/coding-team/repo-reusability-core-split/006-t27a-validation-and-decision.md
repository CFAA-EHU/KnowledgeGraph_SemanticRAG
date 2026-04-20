# Context

T27A is only useful if the new architectural framing does not introduce runtime regressions and ends with a formal decision artifact.

# Objective

Validate the repository after T27A changes and issue the formal T27A cleanup and decision reports.

# Scope

- Run the approved non-regression checks for:
  - compile safety on the key operational modules and entrypoints
  - `QA_canonical`
  - `QA_multihop`
  - `QA_8070_quick_ref_bilingual_v2`
  - `QA_cross`
  - GraphDB healthcheck
- Generate:
  - `data/processed/t27_repo_cleanup_report.json`
  - `data/processed/t27_repo_cleanup_decision_report.json`
- Record whether T27A criteria are satisfied.

# Non-goals / Later

- Do not begin T27B structural isolation work.
- Do not change runtime semantics to chase unrelated quality improvements.

# Constraints / Caveats

- If any baseline regresses, stop and report honestly instead of forcing a green decision.
- GraphDB health must be recorded as part of the final decision.
- The decision report must explicitly state whether the repository is ready to proceed to T27B.

# Acceptance Notes

- This task closes T27A only; it does not declare the repository fully ready for case-specific split unless the approved T27A scope says so.
