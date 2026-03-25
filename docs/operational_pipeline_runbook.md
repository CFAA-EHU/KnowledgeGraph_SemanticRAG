# Operational Pipeline Runbook

## Default entrypoint

```bash
python run_operational_pipeline.py --mode resume-compatible
```

## Pilot onboarding for a new manual

```bash
python run_operational_pipeline.py --source-chunks data/raw/chunks_8070_quick_ref.txt --manual-id 8070_quick_ref --mode resume-compatible
```

This pilot lane writes manual-specific intermediate artifacts first:
- `data/processed/quick_ref_density_report.json`
- `data/processed/quick_ref_language_detection_report.json`
- `data/processed/quick_ref_abox_input.json`
- `data/processed/quick_ref_onboarding_report.json`

If `MISTRAL_API_KEY` is present, the pipeline continues through extraction, merge, canonicalization, enrichment, link completion and lexicon rebuild, publishing into the shared runtime graph.

## Operational build sequence

1. `src/6_extraction/abox_input_builder.py`
2. `src/6_extraction/abox_extractor.py`
3. `src/6_extraction/abox_merger.py`
4. `src/6_extraction/abox_canonicalizer.py`
5. `src/6_extraction/abox_graph_enricher.py`
6. `src/6_extraction/abox_link_completer.py`
7. `src/8_retrieval/multilingual_lexicon_builder.py`

## Runtime contract

The runtime must load:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/multilingual_lexicon.json`

`abox_merged.ttl`, `abox_canonical.ttl` and `abox_enriched.ttl` are diagnostic or intermediate artifacts. They must not be used as the default runtime graph.

## Manual question entrypoint

Primary manual query entrypoint:

```bash
python query_workbench.py "¿Qué directiva cumple la máquina?" --backend rdflib
```

Use `query_workbench.py` when you need:
- plan family
- normalized question
- execution trace
- raw rows
- optional synthesis

Use `embedded_store.py` only for direct SPARQL inspection without planner or synthesis.

## GraphDB mirror backend

GraphDB is an optional mirror backend of the same operational graph:
- default base URL: `http://localhost:7200`
- default repository id: `semanticrag_operational_mirror`
- `rdflib` remains the reference backend and safe fallback

Publish the current operational graph to GraphDB:

```bash
python src/7_database/publish_to_graphdb.py
```

Run the GraphDB healthcheck:

```bash
python src/7_database/graphdb_healthcheck.py
```

Run the basic RDFLib vs GraphDB equivalence check:

```bash
python src/7_database/graph_store.py
```

Run the workbench against GraphDB:

```bash
python query_workbench.py "¿Qué directiva cumple la máquina?" --backend graphdb
```

If GraphDB fails, fall back immediately to RDFLib:

```bash
python query_workbench.py "¿Qué directiva cumple la máquina?" --backend rdflib
```

## Benchmark and diagnostic entrypoints

Formal benchmarks:
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_canonical.json`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_bilingual.json`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_8070_quick_ref_bilingual_v2.json --report-path data/processed/quick_ref_v2_eval_report.json --debug-report-path data/processed/quick_ref_v2_debug_report.json`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_cross.json --report-path data/processed/cross_eval_report.json --debug-report-path data/processed/cross_debug_report.json`

Sandbox diagnostic:
- `python src/8_retrieval/qa_sandbox_diagnostic.py`

## Readiness gates currently in force

Formal baseline:
- `QA_canonical = 13/13`
- `QA_multihop = 7/7`

Planner hardening gates:
- `QA_8070_quick_ref_bilingual_v2.json`
- `QA_cross.json`

Graph backend mirror gates:
- `graphdb_publication_report.json`
- `graphdb_equivalence_report.json`
- `t23_graphdb_decision_report.json`
