# T27 Plan

## Topic

`repo-reusability-core-split`

## Scope

This topic covers the approved T27 split:

- `T27A` — reusable boundary, operational contract, artifact policy
- `T27B` — minimal structural isolation after T27A is validated

## Constraints

- Do not change product behavior intentionally.
- Do not mix T27A and T27B in one implementation wave.
- Do not introduce new manuals, telemetry modeling, or ontology expansion.
- Do not let historical scripts remain documented as operational primary paths.
- Do not perform high-risk physical moves that force broad import rewrites.

## Success Criteria

### T27A

- explicit `core_reusable` vs `project_specific` boundary
- stable operational entrypoint contract
- historical tooling registry
- processed artifact policy and registry
- documentation aligned with the runtime contract
- `historical_tooling_declassified_from_operational_path = true`
- baseline preserved
- GraphDB healthy

### T27B

- historical tooling isolated structurally or semantically
- project-specific assets clearly encapsulated
- repository ready for reuse
- repository ready for later case-specific split
- baseline preserved
- GraphDB healthy

## Proposed Task Sequence

1. Inventory the repository and classify runtime, project, historical, and debug assets.
2. Define the formal core-vs-project policy and the stable operational contract.
3. Define the `data/processed` artifact policy and registry.
4. Align top-level and operational documentation with the approved contract.
5. Validate T27A against the current runtime and GraphDB gates.
6. Identify low-risk structural isolations for historical and project-specific assets.
7. Apply only minimal structural changes that preserve compatibility.
8. Re-validate the runtime after T27B and issue the final decision reports.

## Notes

- `run_t25*`, `run_t26*`, recovery wrappers, and diagnostic scripts are expected to remain in-repo for traceability, but not as operational primary paths.
- `data/raw`, `data/golden_set`, and current accepted-manual artifacts remain project-specific even if temporarily retained in this repository.
- T27B should proceed only after T27A is accepted and green.
