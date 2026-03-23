# Operational Artifact Contract

## Canonical contracts

### Operational lane

- Default build entrypoint: `run_operational_pipeline.py`
- T-Box: `data/processed/ontology_aligned.ttl`
- A-Box input: `data/processed/abox_input.json`
- A-Box manifest: `data/processed/abox_generation_manifest.json`
- A-Box semantic audit: `data/processed/abox_semantic_audit.json`
- Raw merged A-Box: `data/processed/abox_merged.ttl`
- Canonical A-Box: `data/processed/abox_canonical.ttl`
- Enriched operational A-Box: `data/processed/abox_enriched.ttl`
- Canonical entity map: `data/processed/canonical_entity_map.json`
- Canonicalization report: `data/processed/canonicalization_report.json`
- Canonicalization resolution candidates: `data/processed/canonicalization_resolution_candidates.json`
- Enrichment report: `data/processed/enrichment_report.json`
- Enrichment link map: `data/processed/enrichment_link_map.json`
- Enrichment surface map: `data/processed/enrichment_surface_map.json`
- Enrichment resolution candidates: `data/processed/enrichment_resolution_candidates.json`

The default operational build runs `abox_input_builder.py`, `abox_extractor.py`, `abox_merger.py`, `abox_canonicalizer.py`, and `abox_graph_enricher.py` in that order. The runtime graph contract for this phase is `ontology_aligned.ttl` plus `abox_enriched.ttl`.

### Experimental lane

- Dynamic T-Box prompts: `data/processed/tbox_prompts.json`
- Merged experimental ontology: `data/processed/ontology_merged.ttl`
- Optional aligned A-Box: `data/processed/abox_aligned.ttl`

## Operational A-Box contract

`data/processed/abox_merged.ttl` is the raw post-merge snapshot used for diagnostics and structural comparison.

`data/processed/abox_canonical.ttl` is the canonical intermediate A-Box produced by generic entity consolidation.

`data/processed/abox_enriched.ttl` is the final operational A-Box consumed by store, retrieval, evaluation and orchestration.

The canonicalization phase resolves entity clusters and rewrites links toward canonical URIs. The enrichment phase only adds traceable linking/value-surface improvements and must not reactivate duplicate runtime nodes.
