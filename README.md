# SemanticRAG

A framework for constructing operational semantic runtimes from technical manuals. The repository covers ingestion, A-Box extraction, structural graph consolidation, multilingual support, GraphDB publication, and functional evaluation of the resulting runtime.

The repository retains an active reference project based on a broaching machine and CNC 8070 manuals. That corpus and its project-specific tuning are adjuncts to the reusable core, not definitions of it.

## Reusable core

- `src/1_ingestion/` — ingestion and density analysis
- `src/6_extraction/` — operational A-Box construction pipeline
- `src/7_database/` — local RDF backend and GraphDB mirror
- `src/8_retrieval/` — retrieval, evaluation, query normalization
- `artifact_contracts.py` — canonical artifact path registry
- `docs/` — operational runbook and artifact contract

## Project-specific scope

The broaching/CNC 8070 reference project occupies:

- `data/raw/` — source chunk files (A218, 8070 quick-ref, installation, error manual, variables CNC)
- `cache/terms_cache.json` — terminology cache built from the reference corpus
- `data/processed/a218_*`, `quick_ref_*`, `installation_manual_*`, `8070_installation_*`, `man_8070_err_*`, `variables_cnc_*` — per-manual pipeline artifacts
- partial domain-tuning in `src/8_retrieval/text_to_sparql.py`, `multilingual_query_normalizer.py`, `synthesis_pipeline.py`

The canonical boundary declaration for the retained project is at:

- `projects/broaching-cnc-8070/project_scope_manifest.json`

## Entrypoints

### Primary runtime rebuild

```bash
python run_runtime_clean_rebuild.py --mode resume-compatible
```

The only documented primary path for end-to-end reconstruction of the accepted runtime.

### Tactical rebuild and manual onboarding

```bash
python run_operational_pipeline.py --mode resume-compatible
python run_operational_pipeline.py \
    --source-chunks data/raw/chunks_8070_quick_ref.txt \
    --manual-id 8070_quick_ref \
    --mode resume-compatible
```

### GraphDB

```bash
python src/7_database/publish_to_graphdb.py
python src/7_database/graphdb_healthcheck.py
```

### Query workbench

```bash
python query_workbench.py "Which directive does the machine comply with?" --backend rdflib
python query_workbench.py "Which directive does the machine comply with?" --backend graphdb
```

## Runtime artifact contract

The operational runtime consumes:

- `data/processed/ontology_aligned.ttl` — T-Box
- `data/processed/abox_input.json` — A-Box extraction input
- `data/processed/abox_merged.ttl` — raw post-merge A-Box
- `data/processed/abox_canonical.ttl` — canonicalized A-Box
- `data/processed/abox_enriched.ttl` — enriched A-Box
- `data/processed/abox_linked.ttl` — final operational A-Box
- `data/processed/multilingual_lexicon.json` — ES/EN bilingual lexicon

Structural reports and maps (runtime contract):

- `data/processed/canonical_entity_map.json`
- `data/processed/enrichment_report.json`, `enrichment_link_map.json`, `enrichment_surface_map.json`
- `data/processed/link_completion_report.json`, `link_completion_map.json`, `link_completion_candidates.json`
- `data/processed/abox_semantic_audit.json`
- `data/processed/abox_minted_entity_registry.json`
- `data/processed/schema_condensed.txt`
- `data/processed/graphdb_publication_report.json`

## Build sequence

1. `src/1_ingestion/density_analyzer.py`
2. `src/6_extraction/abox_input_builder.py`
3. `src/6_extraction/abox_extractor.py`
4. `src/6_extraction/abox_merger.py`
5. `src/6_extraction/abox_canonicalizer.py`
6. `src/6_extraction/abox_graph_enricher.py`
7. `src/6_extraction/abox_link_completer.py`
8. `src/8_retrieval/multilingual_lexicon_builder.py`

## data/processed artifact classification

| Class | Description |
|---|---|
| `runtime_contract` | Live runtime artifacts |
| `accepted_project_operational_artifact` | Per-manual artifacts for the active reference project |
| `historical_campaign_traceability` | Outputs of completed development campaigns, retained for traceability |
| `debug_and_diagnostics` | Transient audit and diagnostic outputs |

A clean rebuild reconstructs `runtime_contract` artifacts. It preserves and may refresh `accepted_project_operational_artifact`. It does not consume `historical_campaign_traceability` as authoritative input. It may overwrite `debug_and_diagnostics`.

## Semantic quality contract

- `ontology_aligned.ttl` declares permitted classes, properties, and axioms.
- `abox_linked.ttl` materializes individuals and inter-individual links.
- `rdf:type` objects are never minted, canonicalized, or treated as A-Box entities.
- GraphDB publishes the sanitized result; it does not deduplicate or merge by label.

Semantic validation blocks: non-canonical classes or properties, individuals used as classes, domain blank nodes, `file:///` IRIs, redundant explicit types, subjects without type or traceability.

## T-Box enrichment

T-Box enrichment is restricted to axioms over existing vocabulary with runtime evidence. The auditor:

```bash
python src/6_extraction/tbox_enrichment_auditor.py
```

produces `data/processed/t_tbox_enrichment_evidence.json`. After any T-Box change, regenerate the schema condenser:

```bash
python src/8_retrieval/schema_condenser.py
```

## Legacy and experimental lanes

Not part of the default runtime:

- `src/2_extraction/` — experimental T-Box extractor (MistralAI)
- `src/3_merging/` — experimental graph merger
- `src/5_alignment/` — experimental semantic reduction

## Requirements

- Python 3.10 or higher
- `pip install -r requirements.txt`
- GraphDB instance if publishing or querying the remote mirror
- Ollama running locally with Qwen model for A-Box extraction (`apply_ollama_parallel.sh`)

## Documentation

- [docs/operational_pipeline_runbook.md](docs/operational_pipeline_runbook.md)
- [docs/operational_artifact_contract.md](docs/operational_artifact_contract.md)
- [src/6_extraction/README.md](src/6_extraction/README.md)
- [src/7_database/README.md](src/7_database/README.md)
- [src/8_retrieval/README.md](src/8_retrieval/README.md)
