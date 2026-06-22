# docs

Index of contractual and operational documentation for the repository.

## Start here

- [../README.md](../README.md) — framework overview, core vs. project-specific boundary, entrypoints, runtime contract
- [operational_pipeline_runbook.md](operational_pipeline_runbook.md) — stable operational path for rebuild, onboarding, evaluation, query, and GraphDB
- [operational_artifact_contract.md](operational_artifact_contract.md) — artifact contract for the operational lane

## Module documentation

- [../src/6_extraction/README.md](../src/6_extraction/README.md) — A-Box build pipeline and structural snapshot semantics
- [../src/7_database/README.md](../src/7_database/README.md) — local RDF backend, GraphDB mirror, publication and healthcheck
- [../src/8_retrieval/README.md](../src/8_retrieval/README.md) — planner, retrieval, synthesis, evaluation, query workbench

## Documentation contract

The repository documentation must always communicate:

- The repository is a reusable framework with a retained reference project.
- `run_runtime_clean_rebuild.py` is the only documented primary rebuild path.
- `run_operational_pipeline.py` is a stable secondary entrypoint for tactical rebuilds and single-manual onboarding.
- `src/2_extraction/`, `src/3_merging/`, and `src/5_alignment/` are legacy or experimental lanes, not default runtime steps.
- `data/processed` contains artifacts with distinct status: live runtime, accepted project, historical campaign traceability, and diagnostics.
- The project-specific boundary for the retained reference project is declared in `projects/broaching-cnc-8070/`.
