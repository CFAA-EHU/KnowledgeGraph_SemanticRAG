
---

## 2) `c:\Users\Leonardo\Documents\00 Projects\Activos\2026 SemanticOnt\KnowledgeGraph_SemanticRAG\src\8_retrieval\README.md`

```markdown
# src/8_retrieval — Query layer, evaluación y planner multi-hop

Este directorio contiene la capa de recuperación SPARQL y evaluación del runtime operativo.

## Objetivo
Traducir preguntas del usuario a consultas SPARQL útiles sobre el grafo operativo, medir el comportamiento del sistema y separar fallos de:
- cobertura del grafo
- generación de consulta
- boundedness de resultados
- síntesis final

---

## Módulos principales

### `schema_condenser.py`
Lee:
- `data/processed/ontology_aligned.ttl`

Genera:
- `data/processed/schema_condensed.txt`

Sirve para condensar el esquema y facilitar interpretación y debugging del runtime.

### `text_to_sparql.py`
Es el query layer compartido del proyecto.

Responsabilidades actuales:
- parsing determinista de intención
- detección de ancla
- detección de profundidad prevista
- construcción de `QueryPlan`
- soporte de planes explícitos de `1`, `2` y `3` hops
- selección de familias y plantillas de consulta
- ejecución incremental por pasos
- propagación de candidatos entre saltos
- boundedness controlado por paso
- fallback controlado
- trazabilidad completa de la ejecución

El planner multi-hop ya está en producción y es la fuente única de consulta para:
- `qa_evaluator.py`
- `semantic_rag.py`
- `query_workbench.py`

### `qa_evaluator.py`
Evalúa el runtime sobre:
- `data/golden_set/QA_canonical.json`
- `data/golden_set/QA_multihop.json`

Genera:
- `data/processed/qa_eval_report.json`
- `data/processed/qa_failure_analysis.json`
- `data/processed/multihop_eval_report.json`
- `data/processed/multihop_debug_report.json`

Ahora usa el mismo planner compartido que el orquestador.

---

## Artefactos de apoyo

### Queryability y validación canónica
- `data/processed/queryability_target_matrix.json`
- `data/processed/ontology_queryability_audit.json`
- `data/processed/canonical_sparql_suite.json`
- `data/processed/canonical_sparql_execution_report.json`
- `data/processed/canonical_vs_generated_comparison.json`

### Planner multi-hop
- `data/processed/multihop_plan_catalog.json`
- `data/processed/multihop_eval_report.json`
- `data/processed/multihop_debug_report.json`
- `data/processed/multihop_planner_decision_report.json`

### Intents y debugging
- `data/processed/query_intent_catalog.json`
- `data/processed/query_debug_report.json`

---

## Estado actual tras T12

### Ya conseguido
- query layer compartido en producción
- mejora significativa respecto al baseline inicial
- consultas canónicas bounded y usable
- planner multi-hop con familias explícitas
- benchmark multi-hop resuelto con `7/7`
- `avg_recall = 1.0` en el benchmark
- `fallback_count = 0` en el benchmark multi-hop

### Qué sigue siendo el problema
El problema ya no es “si el sistema soporta multi-hop”, sino:
- generalizar el planner a preguntas fuera de las familias seedadas
- afinar boundedness en preguntas no benchmark
- reducir consultas todavía demasiado amplias en algunos casos del dataset general

---

## Diseño actual del planner

El planner ya no genera solo una query plana. Ahora construye:
- intención
- ancla
- familia de plan
- profundidad prevista
- pasos de candidate retrieval y expansión
- controles de boundedness por salto
- trazabilidad de ejecución

El objetivo no es NL→SPARQL general, sino cobertura robusta de familias de consulta reales del dominio.

---

## Benchmarks disponibles

### Dataset canónico general
- `data/golden_set/QA_canonical.json`

### Dataset multi-hop
- `data/golden_set/QA_multihop.json`

Usa el benchmark multi-hop para validar:
- rutas de `2` y `3` hops
- boundedness por paso
- propagación de candidatos
- separación entre fallo de planner y fallo de síntesis