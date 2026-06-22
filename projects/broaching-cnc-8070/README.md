# broaching-cnc-8070

Reference project retained within the SemanticRAG framework repository.

## Scope

This project covers the knowledge graph runtime built from the following manuals:

- A218 (broaching machine operating and maintenance manual)
- Fagor CNC 8070 quick reference
- Fagor CNC 8070 installation manual
- Fagor CNC 8070 error manual
- Fagor CNC 8070 variables manual

## Canonical boundary

The authoritative boundary declaration for all project-specific artifacts is:

- `projects/broaching-cnc-8070/project_scope_manifest.json`

## Project-specific artifacts

- `data/raw/` — source chunk text files
- `cache/terms_cache.json` — terminology cache built from the corpus
- `data/processed/a218_*`, `quick_ref_*`, `installation_manual_*`, `8070_installation_*`, `man_8070_err_*`, `variables_cnc_*`
- Domain-tuned sections of `src/8_retrieval/text_to_sparql.py`, `multilingual_query_normalizer.py`, `synthesis_pipeline.py`

## Runtime status

CQ harness: 46/46 PASS, 6 SKIP (structural gaps in `ex:duracionEstimada`, `ex:requiereHerramienta`, `ex:requierePiezaRecambio`, `ex:tieneEsquema`, `ex:tieneUbicacion`, `ex:version`).

GraphDB repository: `semanticrag_operational_mirror` at `http://localhost:7200`. Triple count after owl:inverseOf materialization: ~85,000.
