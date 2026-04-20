# Runtime Clean Rebuild Plan

## Goal

Rebuild the operational runtime from accepted source manuals and the stable operational pipeline, instead of continuing to accumulate historical campaign wrappers and one-off recovery flows.

The target outcome is a fresh rebuild of:

- `data/processed/abox_input.json`-style operational inputs
- `data/processed/abox_merged.ttl`
- `data/processed/abox_canonical.ttl`
- `data/processed/abox_enriched.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/multilingual_lexicon.json`
- GraphDB operational mirror

using only the stable operational stages:

1. `src/1_ingestion/density_analyzer.py`
2. `src/6_extraction/abox_input_builder.py`
3. `src/6_extraction/abox_extractor.py`
4. `src/6_extraction/abox_merger.py`
5. `src/6_extraction/abox_canonicalizer.py`
6. `src/6_extraction/abox_graph_enricher.py`
7. `src/6_extraction/abox_link_completer.py`
8. `src/8_retrieval/multilingual_lexicon_builder.py`
9. `src/7_database/publish_to_graphdb.py`

## Why a clean rebuild is justified

The current repository state is functionally valid, but the build story is fragmented:

- the default operational entrypoint rebuilds only the legacy default density input
- additional manuals were integrated through historical wrappers and campaign-specific scripts
- canonicalization and extraction policies have evolved after the first builds
- the current runtime contains improvements that would be cleaner if applied from the start of the build

This makes the runtime harder to reason about than it needs to be.

## Accepted source manuals for the clean rebuild

The clean rebuild should include only manuals already accepted into the current operational scope:

- `data/raw/chunks_manual_instrucciones_a218.txt`
- `data/raw/chunks_8070_quick_ref.txt`
- `data/raw/chunks_8070_installation_manual.txt`
- `data/raw/chunks_man_8070_err.txt`

The following manuals should remain out of scope for the rebuild until they are onboarded and accepted explicitly:

- `data/raw/chunks_8070_operating_programming_manual.txt`
- `data/raw/chunks_8070_programming_manual.txt`
- `data/raw/chunks_8070_remote_modules.txt`
- `data/raw/chunks_manual_variables_cnc_8070.txt`
- `data/raw/chunks_dds_soft.txt`

## Current limitation in the stable pipeline

`run_operational_pipeline.py` is a stable operational entrypoint, but today it supports two modes only:

- default rebuild from a single default density report
- pilot onboarding for one manual at a time

It does not yet provide a first-class multi-manual clean rebuild mode.

That is the main gap to close before treating the rebuild as a normal operational action.

## Recommended implementation approach

### Preferred option

Add a stable multi-manual rebuild mode to the operational entrypoint layer.

This can be done in either of these ways:

1. extend `run_operational_pipeline.py` with a `--source-manifest` option
2. add a new stable wrapper such as `run_runtime_clean_rebuild.py` that orchestrates the same stable stages

Both options are acceptable. The important rule is:

- do not base the clean rebuild on `run_t25*`, `run_t26*`, or other historical campaign wrappers

### Recommended source manifest shape

The rebuild manifest should enumerate accepted manuals explicitly, for example:

```json
{
  "manuals": [
    {
      "manual_id": "a218",
      "source_chunks": "data/raw/chunks_manual_instrucciones_a218.txt",
      "artifact_prefix": "a218"
    },
    {
      "manual_id": "8070_quick_ref",
      "source_chunks": "data/raw/chunks_8070_quick_ref.txt",
      "artifact_prefix": "quick_ref"
    },
    {
      "manual_id": "8070_installation",
      "source_chunks": "data/raw/chunks_8070_installation_manual.txt",
      "artifact_prefix": "installation_manual"
    },
    {
      "manual_id": "man_8070_err",
      "source_chunks": "data/raw/chunks_man_8070_err.txt",
      "artifact_prefix": "man_8070_err"
    }
  ]
}
```

## Clean rebuild sequence

### Phase 0. Freeze the current state

Before rebuilding:

- keep the current `data/processed` outputs as a rollback snapshot
- keep the current GraphDB publication report
- do not delete historical reports before the new runtime passes validation

### Phase 1. Refresh shared terminology inputs

Regenerate the shared term cache from the accepted manuals:

- `cache/terms_cache.json`

Then regenerate density reports from source, not from stale cached reports:

- `a218` density report
- `quick_ref` density report
- `installation_manual` density report
- `man_8070_err` density report

Reason:

- `density_analyzer.py` depends on the current terms cache
- density artifacts should reflect the same vocabulary base used for the rebuild

### Phase 2. Build A-Box inputs per manual

Generate one `*_abox_input.json` per accepted manual from its density report.

Do not try to reuse the current monolithic `data/processed/abox_input.json` as the sole truth source for the rebuild.

Reason:

- the stable builder today consumes one density report at a time
- manual-level traceability is useful and already aligns with accepted operational artifacts

### Phase 3. Extract per manual with conservative policy

Run `abox_extractor.py` per manual using:

- `--mode resume-compatible`
- `--retry-profile micro-batch-recovery`

Reason:

- this is the safest default against Mistral rate-limit instability
- it avoids recreating the earlier aggressive extraction failure pattern

If one Mistral model becomes rate-limited, the extractor layer should try the next configured Mistral model instead of failing the entire rebuild immediately.

The operational extractor should therefore use a model chain, not a single fixed model.

Recommended behavior:

- primary model from `MISTRAL_MODEL`
- optional extra models from `MISTRAL_MODEL_FALLBACKS`
- if no explicit fallback chain is configured, use the built-in ordered fallback:
  - `mistral-small-latest`
  - `mistral-medium-latest`
  - `open-mistral-nemo`

The rebuild must continue chunk processing as long as one model in the configured chain remains available.

### Phase 4. Merge raw manual outputs

Produce:

- one raw merged graph per manual
- one operational raw merged graph from the accepted manual set

This merge should happen only from the fresh rebuild outputs, not from historical merged snapshots.

### Phase 5. Rebuild canonical, enriched, and linked graphs

Run the stable structural chain on the fresh merged graph:

1. `abox_canonicalizer.py`
2. `abox_graph_enricher.py`
3. `abox_link_completer.py`

This is where current fixes such as:

- surface-variant canonicalization
- updated enrichment rules
- link-completion policy

will be applied cleanly from the start of the runtime build.

### Phase 6. Rebuild multilingual retrieval support

Regenerate:

- `data/processed/multilingual_lexicon.json`

from the fresh `abox_linked.ttl`.

### Phase 7. Publish and validate

Publish the rebuilt runtime to GraphDB and then execute the validation suite:

- `QA_canonical`
- `QA_multihop`
- `QA_cross`
- `QA_8070_quick_ref_bilingual_v2`
- any accepted manual-specific evaluation report still treated as operationally required

## Artifacts that should be regenerated

At minimum, the clean rebuild should regenerate these operational artifacts:

- `data/processed/abox_input.json`
- `data/processed/abox_generation_manifest.json`
- `data/processed/abox_graphs/*`
- `data/processed/abox_merged.ttl`
- `data/processed/abox_canonical.ttl`
- `data/processed/abox_enriched.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/canonical_entity_map.json`
- `data/processed/canonicalization_report.json`
- `data/processed/canonicalization_resolution_candidates.json`
- `data/processed/enrichment_report.json`
- `data/processed/enrichment_link_map.json`
- `data/processed/enrichment_surface_map.json`
- `data/processed/link_completion_report.json`
- `data/processed/link_completion_map.json`
- `data/processed/link_completion_candidates.json`
- `data/processed/multilingual_lexicon.json`
- `data/processed/graphdb_publication_report.json`

Also regenerate manual-specific density reports, `*_abox_input.json`, manifests, and per-manual chunk directories used as rebuild inputs.

## Intermediate JSON artifacts in `data/processed`

One important constraint for the clean rebuild is that `data/processed` currently mixes several different kinds of JSON files:

1. live runtime contract artifacts
2. accepted manual-level operational artifacts
3. intermediate task reports from historical campaigns
4. transient debug or audit outputs

These categories should not be treated the same way.

### Category A. Live runtime contract JSONs

These are part of the active operational runtime and should be regenerated by the clean rebuild:

- `abox_generation_manifest.json`
- `abox_input.json`
- `abox_semantic_audit.json`
- `canonical_entity_map.json`
- `canonicalization_report.json`
- `canonicalization_resolution_candidates.json`
- `enrichment_report.json`
- `enrichment_link_map.json`
- `enrichment_surface_map.json`
- `link_completion_report.json`
- `link_completion_map.json`
- `link_completion_candidates.json`
- `multilingual_lexicon.json`
- `graphdb_publication_report.json`
- the current evaluation reports used as operational gates, such as:
  - `generalization_eval_report.json`
  - `multihop_eval_report.json`
  - `quick_ref_v2_eval_report.json`
  - `cross_eval_report.json`

### Category B. Accepted manual-level operational JSONs

These are not the single runtime contract, but they are still useful operational artifacts and should be rebuilt from source if they remain part of the accepted runtime scope:

- `quick_ref_density_report.json`
- `quick_ref_abox_input.json`
- `quick_ref_abox_generation_manifest.json`
- `installation_manual_density_report.json`
- `installation_manual_abox_input.json`
- `installation_manual_abox_generation_manifest.json`
- `man_8070_err_density_report.json`
- `man_8070_err_abox_input.json`
- `man_8070_err_abox_generation_manifest.json`

Also include accepted manual decision and evaluation reports when they are still used to justify that a manual belongs in the runtime:

- `quick_ref_integration_decision_report.json`
- `8070_installation_decision_report.json`
- `man_8070_err_decision_report.json`
- their associated evaluation reports

### Category C. Historical intermediate task JSONs

These should be kept for traceability, but they must not define the clean rebuild path and must not be treated as sources of truth for the runtime.

This includes, for example:

- `t21_*`
- `t22_*`
- `t23_*`
- `t24_*`
- `t25_*`
- `t26_*`
- `runtime_non_operational_inventory.json`
- `runtime_cleanup_second_pass_report.json`

It also includes campaign-specific recovery, routing, sync, and closure reports created to complete earlier tasks.

These artifacts are valuable as project history, but the clean rebuild should never consume them as inputs.

### Category D. Transient debug and audit JSONs

These may be useful during the rebuild, but they should be treated as diagnostics, not as authoritative runtime state:

- `qa_failure_analysis.json`
- `query_debug_report.json`
- `synthesis_debug_report.json`
- `bilingual_debug_report.json`
- `cross_debug_report.json`
- `multihop_debug_report.json`
- manual-specific `*_debug_report.json`
- ad hoc audit reports created during recovery or investigation

They may be regenerated, overwritten, or archived depending on the rebuild workflow.

## Policy for `data/processed` during the clean rebuild

The clean rebuild should use this rule:

- rebuild Category A from scratch
- rebuild Category B for the accepted manuals in scope
- preserve Category C as historical traceability, but exclude it from the rebuild contract
- allow Category D to be overwritten or refreshed as part of validation

That means `data/processed` should stop being interpreted as a single flat namespace where every JSON has the same status.

Conceptually, the rebuild should treat it as:

- active runtime state
- accepted manual onboarding state
- historical campaign traceability
- transient debug state

## Post-rebuild recommendation for processed JSON organization

Once the clean rebuild passes validation, the repository should make this distinction explicit.

The minimum acceptable outcome is documentary:

- clearly document which JSONs are live runtime artifacts
- clearly document which JSONs are historical task outputs

The better long-term outcome is structural:

- keep live runtime JSONs in the main `data/processed` contract
- move or archive historical campaign JSONs into a dedicated sub-area such as `data/processed/history/`

This move should happen only after the clean rebuild is successful, so we do not mix cleanup risk with rebuild risk.

## Artifacts that should not define the rebuild path

These should remain historical or utility scripts, not the runtime rebuild contract:

- `run_t25_sequential_integration.py`
- `run_t25_2_installation_recovery.py`
- `run_t26_error_manual_onboarding.py`
- `check_mistral_api_usage.py`

They may still be retained for traceability or diagnostics, but they should not be the normal path to rebuild the operational runtime.

## Repository cleanup after rebuild

Once the rebuilt runtime passes validation:

- keep historical reports for traceability
- keep campaign wrappers clearly classified as historical tooling
- document one stable rebuild path only

The repo should then present these layers clearly:

- stable runtime build
- stable runtime consumption
- experimental legacy tooling
- historical campaign tooling

## Recommendation

The next concrete change should be:

- implement one stable multi-manual clean rebuild entrypoint based on the accepted manual set and the existing operational stages

After that, run the rebuild once end-to-end, validate it, publish it, and only then consider pruning or archiving more historical processed artifacts.
