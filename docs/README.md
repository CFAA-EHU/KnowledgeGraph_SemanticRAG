# docs

Documentacion operativa, contractual y transversal del proyecto.

## Documentos principales

- `operational_artifact_contract.md`
  Contrato de artefactos del carril operativo y experimental, incluyendo desde T20 la lexicalizacion multilingue ES/EN sobre el mismo grafo linked.

- `operational_pipeline_runbook.md`
  Guia de ejecucion del build operativo, ya con las fases post-merge de canonicalizacion, enrichment residual, link completion residual y reconstruccion del lexicon bilingue.

## Relacion con T16-T19

La documentacion de detalle del planner, retrieval y sintesis vive en los README de modulo:
- `README.md`
- `src/6_extraction/README.md`
- `src/8_retrieval/README.md`
- `src/9_rag_orchestrator/README.md`

Los artefactos operativos y diagnosticos relevantes viven en `data/processed/`:
- `abox_merged.ttl`
- `abox_canonical.ttl`
- `abox_enriched.ttl`
- `abox_linked.ttl`
- `canonical_entity_map.json`
- `canonicalization_report.json`
- `canonicalization_resolution_candidates.json`
- `canonicalization_eval_report.json`
- `canonicalization_decision_report.json`
- `enrichment_report.json`
- `enrichment_link_map.json`
- `enrichment_surface_map.json`
- `enrichment_resolution_candidates.json`
- `enrichment_eval_report.json`
- `enrichment_decision_report.json`
- `link_completion_report.json`
- `link_completion_map.json`
- `link_completion_candidates.json`
- `link_completion_eval_report.json`
- `link_completion_decision_report.json`
- `multilingual_lexicon.json`
- `language_detection_report.json`
- `bilingual_eval_report.json`
- `bilingual_debug_report.json`
- `bilingual_decision_report.json`
- `sandbox_diagnostic_report.json`
- `sandbox_structural_gap_summary.json`
- `sandbox_entity_resolution_candidates.json`
- `sandbox_promotion_candidates.json`
- `sandbox_decision_report.json`

## Recomendacion

Mantener aqui solo documentacion estable y transversal. La evolucion del planner, retrieval y sintesis sigue documentandose en los README de modulo, mientras que benchmark formal, sandbox batch, canonicalizacion, enrichment, link completion y soporte bilingue deben tratarse como flujos estructurales separados.
