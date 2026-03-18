# docs

Documentacion operativa, contractual y transversal del proyecto.

## Documentos principales

- `operational_artifact_contract.md`
  Contrato de artefactos del carril operativo y experimental.

- `operational_pipeline_runbook.md`
  Guia de ejecucion del build operativo.

## Relacion con T14-T15

La documentacion de detalle del planner, retrieval y sintesis vive en los README de modulo:
- `README.md`
- `src/8_retrieval/README.md`
- `src/9_rag_orchestrator/README.md`

Los artefactos operativos que resumen T14-T15 viven en `data/processed/`:
- `synthesis_error_taxonomy.json`
- `value_normalization_rules.json`
- `surface_rendering_rules.json`
- `synthesis_eval_report.json`
- `synthesis_debug_report.json`
- `surface_polish_eval_report.json`
- `surface_polish_decision_report.json`

## Recomendacion

Mantener aqui solo documentacion estable y transversal. La evolucion del planner, retrieval y sintesis debe seguir documentandose en los README de los modulos afectados.
