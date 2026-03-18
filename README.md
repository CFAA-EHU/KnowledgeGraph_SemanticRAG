# KnowledgeGraph_SemanticRAG

Pipeline operativo y experimental para convertir manuales tecnicos industriales en un knowledge graph RDF/OWL consultable con SPARQL y reutilizable en un Semantic RAG trazable.

El caso de uso actual es el manual de la brochadora electromecanica A218 / RASHEM - 7x3000x500.

## Carriles del repositorio

### Carril operativo
Es el camino oficial de build, consulta y evaluacion.

Artefactos canonicos:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_input.json`
- `data/processed/abox_merged.ttl`
- `data/processed/schema_condensed.txt`
- `data/golden_set/QA_canonical.json`
- `data/golden_set/QA_multihop.json`

### Carril experimental
Se conserva para exploracion, pero no define el runtime por defecto.

## Build operativo

Entrypoint oficial:
- `python run_operational_pipeline.py --mode resume-compatible`

El flujo ejecuta:
- `src/6_extraction/abox_input_builder.py`
- `src/6_extraction/abox_extractor.py`
- `src/6_extraction/abox_merger.py`

## Query layer tras T13

El planner compartido vive en `src/8_retrieval/text_to_sparql.py` y ahora:
- mantiene el benchmark multi-hop en `7/7`
- generaliza fuera de las familias seedadas del benchmark
- usa normalizacion de anclas y variantes lexicas
- aplica boundedness explicito por familia
- emite confianza, accion recomendada y boundedness final
- alimenta sin divergencia a `qa_evaluator.py`, `semantic_rag.py` y `query_workbench.py`

Artefactos principales de T13:
- `data/processed/planner_generalization_catalog.json`
- `data/processed/boundedness_policy_matrix.json`
- `data/processed/query_regression_set.json`
- `data/processed/generalization_eval_report.json`
- `data/processed/planner_generalization_decision_report.json`

## Estado actual

- `QA_multihop` sigue en `7/7`, con `fallback_count = 0`
- `QA_canonical` queda resuelto con `13/13`
- el planner ya no es el cuello de botella principal del runtime actual
- el siguiente cuello de botella pasa a ser el pulido de sintesis y normalizacion de valores en la respuesta final

## Workbench

`query_workbench.py` sirve para probar preguntas nuevas y ver:
- intencion y ancla detectadas
- familia y profundidad previstas
- confianza del plan
- boundedness por paso y final
- pruning, fallback y gap provisional
- resultados crudos y, opcionalmente, sintesis

## Fuente unica de verdad

Las rutas y artefactos compartidos viven en `artifact_contracts.py`.
