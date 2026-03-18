# Operational Pipeline Runbook

## Default build

Run the canonical operational build from the repository root:

```powershell
python run_operational_pipeline.py
```

The default extractor mode is `resume-compatible`.

## Extractor modes

Use one of these modes when you need a different A-Box regeneration policy:

```powershell
python run_operational_pipeline.py --mode resume-compatible
python run_operational_pipeline.py --mode force-stale
python run_operational_pipeline.py --mode force-all
```

## Controlled semantic sampling

When you need to re-run only representative chunks while tuning semantic quality, call the extractor directly with an explicit chunk list:

```powershell
python src/6_extraction/abox_extractor.py --mode resume-compatible --chunk-ids 27,56,132,143,183,187,188
```

This keeps the compatibility contract intact while letting you validate prompt and semantic-guardrail changes on a bounded sample.

## What the entrypoint runs

The build entrypoint orchestrates exactly these operational stages:

1. `src/6_extraction/abox_input_builder.py`
2. `src/6_extraction/abox_extractor.py`
3. `src/6_extraction/abox_merger.py`

## Required prerequisites

The build fails early if any critical prerequisite is missing:

- canonical T-Box: `data/processed/ontology_aligned.ttl`
- API credentials: `MISTRAL_API_KEY`

## Outputs produced by the operational build

- `data/processed/abox_input.json`
- `data/processed/abox_generation_manifest.json`
- `data/processed/abox_semantic_audit.json`
- `data/processed/abox_merged.ttl`

## Semantic quality checks

Use the lightweight semantic audit after a build or controlled sample refresh:

```powershell
python src/6_extraction/abox_semantic_validator.py
```

The audit flags:

- non-canonical classes
- non-canonical properties
- described subjects without `rdf:type`
- extracted individuals without `ex:textoExtracto`
- weakly linked or relation-free chunks

## After build

Operational consumers remain separate from the build entrypoint:

- `src/7_database/embedded_store.py`
- `src/8_retrieval/schema_condenser.py`
- `src/8_retrieval/qa_evaluator.py`
- `src/9_rag_orchestrator/semantic_rag.py`

Those consumers use the canonical runtime artifacts and are intentionally not launched by default during build.
