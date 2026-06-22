# src/6_extraction

Operational A-Box construction pipeline. Transforms manual chunk files into a single consolidated, canonicalized, and enriched operational A-Box graph.

## Pipeline stages

### abox_input_builder.py

Reads `data/processed/abox_input.json` (or per-manual `*_abox_input.json`) and produces the structured extraction input. Each entry carries chunk text, page references, section metadata, and extraction policy flags.

### abox_extractor.py

Sends each chunk to a local Ollama model (Qwen, prompt version `semantic-guardrails-v5-predicate-rules`) and receives Turtle-formatted A-Box triples. Supports four retry profiles: `standard`, `rate-limit-drain`, `micro-batch-recovery`, `local-high-throughput`. Outputs per-chunk TTL files to `data/processed/abox_graphs/` and a resume manifest at `data/processed/abox_generation_manifest.json`.

Resume behavior controlled by `--mode`: `resume-compatible` skips chunks already in the manifest with a valid hash; `force-stale` re-runs stale chunks; `force-all` re-runs all chunks.

### abox_merger.py

Merges per-chunk TTL files into `data/processed/abox_merged.ttl`. Applies per-graph and aggregate sanitization (blank node removal, `file:///` IRI purging, redundant type removal). Identifies URI collisions and writes `data/processed/abox_merger_identifier_collisions.json`.

### abox_canonicalizer.py

Resolves entity clusters to canonical URIs using `data/processed/canonical_anchors.json` and a resolution policy from `canonical_resolution_policy.py`. Produces `data/processed/abox_canonical.ttl` and `data/processed/canonical_entity_map.json`.

Anchors whose `canonical_uri` is absent from the current graph are skipped (enables partial per-manual rebuilds without cross-manual anchor failures).

### abox_graph_enricher.py

Applies evidence-based link additions and surface improvements from `enrichment_policy.py`. Produces `data/processed/abox_enriched.ttl`.

### abox_link_completer.py

Materializes a small whitelist of residual high-confidence edges from `link_completion_policy.py` (7 family rules). Produces `data/processed/abox_linked.ttl`, the final operational A-Box.

### abox_semantic_validator.py

Validates A-Box graphs against the T-Box vocabulary. Blocks: non-canonical classes or properties, individuals used as classes, blank nodes, `file:///` IRIs, redundant types, subjects without type or traceability.

### tbox_enrichment_auditor.py

Audits the T-Box for safe enrichment candidates (axioms over existing vocabulary with runtime evidence). Produces `data/processed/t_tbox_enrichment_evidence.json`.

### relation_validator.py

Validates semantic coherence of relations in merged TTL files against the T-Box. Reports orphan predicates (A-Box only), dead predicates (T-Box only), domain/range violations, and inverse asymmetry.

```bash
python src/6_extraction/relation_validator.py \
    --tbox data/processed/ontology_aligned.ttl \
    --abox data/processed/a218_merged.ttl data/processed/variables_cnc_merged.ttl \
    --json-out data/processed/relation_validation_report.json
```

## Support modules

- `abox_graph_sanitizer.py` — low-level RDF sanitization utilities and minted entity registry
- `abox_resume_policy.py` — manifest-based resume logic
- `abox_ttl_validator.py` — Turtle syntax validation
- `canonical_resolution_policy.py` — URI resolution and cluster merge rules
- `enrichment_policy.py` — enrichment candidate definitions
- `link_completion_policy.py` — residual link family rules
- `abox_merger_chunk_sanitization.py` — chunk-level sanitization utilities

## A-Box structural snapshots

| File | Description |
|---|---|
| `abox_merged.ttl` | Raw post-merge snapshot; used for diagnostics and structural comparison |
| `abox_canonical.ttl` | Post-canonicalization; entity clusters resolved to canonical URIs |
| `abox_enriched.ttl` | Post-enrichment; residual linking and surface improvements applied |
| `abox_linked.ttl` | Final operational A-Box; consumed by store, retrieval, evaluation, and GraphDB |
