# tests

Unit tests for the operational pipeline components.

## Test files

- `test_abox_canonicalizer.py` — canonicalization policy, anchor resolution, URI cluster merging
- `test_abox_enrichment_guards.py` — enrichment guard conditions and link addition logic
- `test_abox_extractor_identity_guardrails.py` — extractor identity guardrails (predicate direction, type constraints)
- `test_abox_graph_sanitizer.py` — graph sanitization utilities (blank node removal, IRI normalization)
- `test_abox_merger_chunk_sanitization.py` — per-chunk sanitization during merge
- `test_abox_semantic_validator.py` — semantic validation against the T-Box vocabulary
- `test_canonical_resolution_policy.py` — canonical resolution policy rules
- `test_tbox_enrichment_auditor.py` — T-Box enrichment auditor evidence collection
- `test_text_to_sparql_seed_resolution.py` — seed term resolution and plan selection

## Running tests

```bash
python -m pytest tests/
```

All tests are designed to run without a live GraphDB instance or Ollama process.
