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

## Runtime tras T14

El query layer compartido sigue viviendo en `src/8_retrieval/text_to_sparql.py`, pero el runtime ya no termina en los resultados SPARQL crudos.

Ahora el carril operativo completo incluye:
- planner compartido con boundedness y multi-hop
- seleccion post-retrieval de evidencia
- normalizacion determinista de valores
- renderizado final trazable y depurable

Artefactos principales de T14:
- `data/processed/synthesis_error_taxonomy.json`
- `data/processed/value_normalization_rules.json`
- `data/processed/synthesis_eval_report.json`
- `data/processed/synthesis_debug_report.json`
- `data/processed/synthesis_decision_report.json`

## Estado actual

- `QA_multihop` sigue en `7/7`, con `fallback_count = 0`
- `QA_canonical` sigue en `13/13`
- `avg_precision` en `QA_canonical` sube a `0.2643`
- el planner deja de ser el cuello de botella principal del runtime actual
- el residuo pasa a ser pulido fino de superficie y formulacion de algunas respuestas largas

## Workbench

`query_workbench.py` sirve para probar preguntas nuevas y ver:
- intencion y ancla detectadas
- familia y profundidad previstas
- confianza del plan
- boundedness por paso y final
- pruning, fallback y gap provisional
- evidencia recuperada
- evidencia seleccionada para sintesis
- valores normalizados y respuesta final

## Fuente unica de verdad

Las rutas y artefactos compartidos viven en `artifact_contracts.py`.
