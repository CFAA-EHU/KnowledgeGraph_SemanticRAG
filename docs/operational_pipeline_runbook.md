# Operational Pipeline Runbook

## Default entrypoint

```bash
python run_operational_pipeline.py --mode resume-compatible
```

## Operational build sequence

1. `src/6_extraction/abox_input_builder.py`
2. `src/6_extraction/abox_extractor.py`
3. `src/6_extraction/abox_merger.py`
4. `src/6_extraction/abox_canonicalizer.py`
5. `src/6_extraction/abox_graph_enricher.py`

## Output expectations

After a successful run, the operational lane should contain:
- `data/processed/abox_merged.ttl`
- `data/processed/abox_canonical.ttl`
- `data/processed/abox_enriched.ttl`
- `data/processed/canonical_entity_map.json`
- `data/processed/canonicalization_report.json`
- `data/processed/enrichment_report.json`
- `data/processed/enrichment_link_map.json`
- `data/processed/enrichment_surface_map.json`

## Runtime contract

The runtime must load:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_enriched.ttl`

`abox_merged.ttl` and `abox_canonical.ttl` are diagnostic and intermediate artifacts. They must not be used as the default runtime graph.

## Post-build validation

Recommended checks after structural changes:
- `python src/8_retrieval/qa_evaluator.py`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json`
- `python src/8_retrieval/qa_sandbox_diagnostic.py`
