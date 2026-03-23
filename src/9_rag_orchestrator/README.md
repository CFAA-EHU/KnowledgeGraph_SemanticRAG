# src/9_rag_orchestrator

Capa conversacional final del Semantic RAG operativo.

## Script principal

### `semantic_rag.py`
Consume:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/schema_condensed.txt`
- el planner compartido de `src/8_retrieval/text_to_sparql.py`
- la sintesis compartida de `src/8_retrieval/synthesis_pipeline.py`

## Responsabilidades
- recibir la pregunta del usuario
- construir y ejecutar el mismo `QueryPlan` compartido que usa el evaluador
- trabajar sobre entidades canonicas, enriquecidas y enlazadas residualmente
- mostrar familia, confianza, boundedness y accion recomendada
- ejecutar la sintesis explicita por fases auditables
- dejar trazabilidad suficiente para separar fallo de planner, linking y sintesis

## Estado tras T19

El orquestador opera sobre el snapshot linked y hereda:
- planner compartido
- sintesis compartida
- consolidacion canonica previa
- enrichment residual de linking y value surfaces
- link completion residual restringido a las familias reales detectadas en sandbox
- trazabilidad mas clara entre fallo de consulta, fallo estructural y fallo de surface rendering

## Uso con preguntas nuevas

Para depurar primero planner y boundedness, usa `query_workbench.py`.
Cuando quieras ver un lote completo sin `expected_uris`, usa `python src/8_retrieval/qa_sandbox_diagnostic.py`.
Cuando el plan ya sea razonable, usa `semantic_rag.py` para comprobar si la sintesis comparte bien la misma evidencia y la verbaliza con calidad suficiente sobre el grafo linked.
