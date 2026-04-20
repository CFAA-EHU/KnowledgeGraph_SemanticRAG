# Historical Tooling

This area groups scripts and planning artifacts that remain useful for traceability or diagnostics but are not part of the primary operational runtime path.

Subareas:

- `campaigns/`: campaign-specific wrappers such as `run_t25*` and `run_t26*`
- `diagnostics/`: smoke-test or provider utilities such as `check_mistral_api_usage.py`

Compatibility notes:

- Root-level compatibility shims remain in place for historical wrappers and the diagnostic utility.
- `docs/runtime_clean_rebuild_plan.md` remains as a stub that points here.
- `misc/coding-team/repo-reusability-core-split/` is still retained in place while the T27 planning traceability is active, but it is not part of the operational path.
