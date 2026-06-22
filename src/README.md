# src

Source code for the SemanticRAG pipeline. Organized by pipeline stage number.

## Operational pipeline

| Directory | Stage | Description |
|---|---|---|
| `1_ingestion/` | 1 | Density analysis, terminology loading, chunk filtering |
| `6_extraction/` | 2–6 | A-Box extraction, merge, canonicalization, enrichment, link completion |
| `7_database/` | 7 | Local RDF backend and GraphDB mirror |
| `8_retrieval/` | 8 | Query planning, retrieval, synthesis, evaluation |
| `9_rag_orchestrator/` | 9 | Top-level RAG orchestration |
| `tools/` | — | Standalone repair and maintenance utilities |

## Legacy and experimental lanes

| Directory | Description |
|---|---|
| `2_extraction/` | Experimental T-Box extractor (MistralAI) |
| `3_merging/` | Experimental graph merger |
| `5_alignment/` | Experimental semantic reduction |

Numbers 4 are reserved (alignment stage absorbed into `5_alignment/`).
