# docs

Documentacion operativa, contractual y transversal del proyecto.

## Documentos principales

- `operational_artifact_contract.md`
  Contrato de artefactos del carril operativo y experimental.

- `operational_pipeline_runbook.md`
  Guia de ejecucion del build operativo.

## Relacion con T13

La documentacion de detalle del planner generalizado y de boundedness vive ya en los README de modulo:
- `README.md`
- `src/8_retrieval/README.md`
- `src/9_rag_orchestrator/README.md`

Los artefactos operativos que resumen T13 viven en `data/processed/`:
- `planner_generalization_catalog.json`
- `boundedness_policy_matrix.json`
- `query_regression_set.json`
- `generalization_eval_report.json`
- `planner_generalization_decision_report.json`

## Recomendacion

Mantener aqui solo documentacion estable y transversal. La evolucion del planner y del runtime debe seguir documentandose en los README de los modulos afectados.
