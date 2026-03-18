# src/8_retrieval

Capa de recuperacion SPARQL, evaluacion y planner compartido del runtime operativo.

## Componentes principales

### `schema_condenser.py`
Genera `data/processed/schema_condensed.txt` a partir de `data/processed/ontology_aligned.ttl`.

### `text_to_sparql.py`
Es la fuente unica de planificacion de consulta del proyecto.

Responsabilidades actuales:
- parsing determinista de intencion
- normalizacion de anclas y variantes lexicas
- seleccion de familias benchmarkeadas y generalizadas
- construccion de `QueryPlan` por pasos
- soporte de 1, 2 y 3 hops
- propagacion de candidatos entre saltos
- boundedness por familia y por paso
- confianza del plan y accion recomendada
- fallback controlado
- export de catalogos y matriz de boundedness

Artefactos que exporta o alimenta:
- `data/processed/multihop_plan_catalog.json`
- `data/processed/planner_generalization_catalog.json`
- `data/processed/boundedness_policy_matrix.json`
- `data/processed/query_debug_report.json`
- `data/processed/multihop_debug_report.json`

### `qa_evaluator.py`
Evalua el runtime operativo sobre:
- `data/golden_set/QA_canonical.json`
- `data/golden_set/QA_multihop.json`

Genera:
- `data/processed/generalization_eval_report.json`
- `data/processed/qa_failure_analysis.json`
- `data/processed/multihop_eval_report.json`
- `data/processed/query_regression_set.json`
- `data/processed/planner_generalization_decision_report.json`

## Estado tras T13

### Lo ya conseguido
- planner multi-hop compartido estable
- `QA_multihop` conservado en `7/7`
- `QA_canonical` resuelto en `13/13`
- nuevas familias generalizadas para figura de cabecera, simbolos de seguridad, contacto EKIN, recambios y directiva CE
- boundedness explicito por politica
- confianza y accion recomendada visibles en evaluacion y workbench

### Lo que sigue pendiente
El cuello de botella principal ya no es el planner, sino:
- pulido de sintesis final
- normalizacion de respuestas literales
- presentacion mas natural de identificadores y valores

## Regresion obligatoria

Antes de cerrar cambios en esta capa, ejecutar al menos:
- `python src/8_retrieval/qa_evaluator.py`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json`
- `python src/8_retrieval/text_to_sparql.py --export-generalization-catalog`
- `python src/8_retrieval/text_to_sparql.py --export-boundedness-matrix`
