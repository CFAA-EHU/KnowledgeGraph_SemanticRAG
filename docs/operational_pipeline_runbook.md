# Operational Pipeline Runbook

## Primary runtime rebuild

```bash
python run_runtime_clean_rebuild.py --mode resume-compatible
```

The primary entrypoint for multi-manual end-to-end reconstruction of the accepted runtime, including validation and optional GraphDB publication.

Supported modes: `resume-compatible`, `force-stale`, `force-all`.

Supported retry profiles: `standard`, `rate-limit-drain`, `micro-batch-recovery`, `local-high-throughput`.

The extractor uses an Ollama model chain with per-model fallback. A failure on one model triggers the next before declaring a chunk failure.

## Tactical rebuild and manual onboarding

`run_operational_pipeline.py` is a stable secondary entrypoint for lower-scope rebuilds and single-manual onboarding.

```bash
python run_operational_pipeline.py --mode resume-compatible
python run_operational_pipeline.py \
    --source-chunks data/raw/chunks_8070_quick_ref.txt \
    --manual-id 8070_quick_ref \
    --mode resume-compatible
```

## Build sequence

1. `src/1_ingestion/density_analyzer.py`
2. `src/6_extraction/abox_input_builder.py`
3. `src/6_extraction/abox_extractor.py`
4. `src/6_extraction/abox_merger.py`
5. `src/6_extraction/abox_canonicalizer.py`
6. `src/6_extraction/abox_graph_enricher.py`
7. `src/6_extraction/abox_link_completer.py`
8. `src/8_retrieval/multilingual_lexicon_builder.py`

## Runtime artifact contract

Primary runtime inputs:

- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/multilingual_lexicon.json`

Build intermediates:

- `data/processed/abox_input.json`
- `data/processed/abox_merged.ttl`
- `data/processed/abox_canonical.ttl`
- `data/processed/abox_enriched.ttl`

Structural maps and reports:

- `data/processed/canonical_entity_map.json`
- `data/processed/enrichment_report.json`, `enrichment_link_map.json`, `enrichment_surface_map.json`
- `data/processed/link_completion_report.json`, `link_completion_map.json`, `link_completion_candidates.json`
- `data/processed/graphdb_publication_report.json`

## data/processed classification

1. `runtime_contract` — a clean rebuild reconstructs these
2. `accepted_project_operational_artifact` — preserved and may be refreshed
3. `historical_campaign_traceability` — not consumed as authoritative rebuild input
4. `debug_and_diagnostics` — may be overwritten

## GraphDB mirror

GraphDB mirrors the same operational graph. `rdflib` remains the reference backend.

```bash
python src/7_database/publish_to_graphdb.py
python src/7_database/graphdb_healthcheck.py
python src/7_database/graph_store.py   # basic equivalence check
```

## Query workbench

```bash
python query_workbench.py "Which directive does the machine comply with?" --backend rdflib
python query_workbench.py "Which directive does the machine comply with?" --backend graphdb
```

`query_workbench.py` displays normalized query, plan family, predicted boundedness, retrieved evidence, and synthesized answer.

## Competency question harness

```bash
python src/tools/run_cq_harness.py
```

Evaluates all 52 CQs against the live GraphDB graph. Final accepted score: 46/46 PASS, 6 SKIP (structural gaps).

## Legacy paths

Not part of the primary operational path:

- `src/2_extraction/` — experimental T-Box extractor
- `src/3_merging/` — experimental graph merger
- `src/5_alignment/` — experimental semantic reduction
