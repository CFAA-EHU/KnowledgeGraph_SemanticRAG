# src/8_retrieval — Query layer, evaluación y validación de queryability

Este directorio contiene la capa de recuperación SPARQL y evaluación del runtime.

## Objetivo
Traducir preguntas del usuario a consultas SPARQL útiles sobre el grafo operativo, medir el comportamiento del sistema y separar fallos de:
- cobertura del grafo
- generación de consulta
- boundedness de resultados
- síntesis final

## Módulos principales

### `schema_condenser.py`
Lee:
- `data/processed/ontology_aligned.ttl`

Genera:
- `data/processed/schema_condensed.txt`

Sirve para resumir el esquema y facilitar tareas de interpretación del runtime.

### `text_to_sparql.py`
Es el query layer compartido del proyecto.

Responsabilidades actuales:
- parsing determinista de intención
- detección de ancla
- generación de `QueryPlan`
- selección de plantillas `T1` a `T6`
- recuperación en dos fases cuando aplica
- fallback controlado
- trazabilidad operativa del plan de consulta

### `qa_evaluator.py`
Evalúa el runtime contra:
- `data/golden_set/QA_canonical.json`

Genera:
- `data/processed/qa_eval_report.json`
- `data/processed/qa_failure_analysis.json`

Además, ahora usa el query layer compartido en vez de generar consultas con lógica separada.

## Artefactos de apoyo
- `data/processed/query_intent_catalog.json`
- `data/processed/query_debug_report.json`
- `data/processed/queryability_target_matrix.json`
- `data/processed/ontology_queryability_audit.json`
- `data/processed/canonical_sparql_suite.json`
- `data/processed/canonical_sparql_execution_report.json`
- `data/processed/canonical_vs_generated_comparison.json`

## Estado actual tras T10–T11
- query layer compartido en producción
- mejora significativa frente al baseline anterior
- suite de consultas SPARQL canónicas validada
- comparación explícita entre consulta generada y consulta canónica
- benchmark multi-hop separado del golden set general

## Limitación actual
El siguiente cuello de botella principal ya no es el grafo, sino el planner multi-hop y el ajuste fino de boundedness en algunos tipos de pregunta.