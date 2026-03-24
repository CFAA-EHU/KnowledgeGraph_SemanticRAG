# docs

Documentacion operativa, contractual y transversal del proyecto.

## Documentos principales

- `operational_artifact_contract.md`
  Contrato de artefactos del carril operativo y experimental, incluyendo desde T20 la lexicalizacion multilingue ES/EN sobre el mismo grafo linked.

- `operational_pipeline_runbook.md`
  Guia de ejecucion del build operativo, ya con las fases post-merge de canonicalizacion, enrichment residual, link completion residual, reconstruccion del lexicon bilingue y onboarding piloto de manual ingles.

## Infraestructura de almacenamiento y consulta

Tras T23, el proyecto incorpora GraphDB como pieza de infraestructura adicional:
- almacenamiento remoto del grafo operativo ya materializado
- consulta SPARQL remota sobre el mismo snapshot operativo
- exploracion visual del grafo cuando GraphDB este disponible

Importante:
- GraphDB entra como backend espejo
- `rdflib` sigue siendo el backend de referencia
- no se introduce todavia una migracion total del runtime

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
- `quick_ref_density_report.json`
- `quick_ref_abox_input.json`
- `quick_ref_onboarding_report.json`
- `quick_ref_bilingual_eval_report.json`
- `quick_ref_bilingual_debug_report.json`
- `quick_ref_integration_decision_report.json`
- `quick_ref_v2_eval_report.json`
- `quick_ref_v2_debug_report.json`
- `quick_ref_v2_planner_alignment_report.json`
- `cross_eval_report.json`
- `cross_debug_report.json`
- `cross_planner_alignment_report.json`
- `planner_generalization_catalog_v2.json`
- `cross_plan_catalog.json`
- `t22_planner_eval_report.json`
- `t22_planner_decision_report.json`
- `graphdb_publication_report.json`
- `graphdb_equivalence_report.json`
- `t23_graphdb_decision_report.json`
- `sandbox_diagnostic_report.json`
- `sandbox_structural_gap_summary.json`
- `sandbox_entity_resolution_candidates.json`
- `sandbox_promotion_candidates.json`
- `sandbox_decision_report.json`

## Recomendacion

Mantener aqui solo documentacion estable y transversal. La evolucion del planner, retrieval y sintesis sigue documentandose en los README de modulo, mientras que benchmark formal, sandbox batch, canonicalizacion, enrichment, link completion y soporte bilingue deben tratarse como flujos estructurales separados.

Tras T22, el readiness post-planner queda gobernado por dos gates separados y no agregables:
- `QA_8070_quick_ref_bilingual_v2.json`
- `QA_cross.json`

La trazabilidad fina de alineacion vive en `quick_ref_v2_planner_alignment_report.json` y `cross_planner_alignment_report.json`, mientras que la decision ejecutiva final vive en `t22_planner_decision_report.json`.
