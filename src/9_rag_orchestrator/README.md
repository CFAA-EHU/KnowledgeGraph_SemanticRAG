# src/9_rag_orchestrator

Capa conversacional final del Semantic RAG operativo.

## Script principal

### `semantic_rag.py`
Consume:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/multilingual_lexicon.json`
- `data/processed/schema_condensed.txt`
- el planner compartido de `src/8_retrieval/text_to_sparql.py`
- la sintesis compartida de `src/8_retrieval/synthesis_pipeline.py`

## Responsabilidades
- recibir la pregunta del usuario
- construir y ejecutar el mismo `QueryPlan` compartido que usa el evaluador
- trabajar sobre entidades canonicas, enriquecidas y enlazadas residualmente
- detectar ES/EN y normalizar ambas al mismo plan canonico
- mostrar familia, confianza, boundedness y accion recomendada
- ejecutar la sintesis explicita por fases auditables
- devolver la respuesta en el idioma de la pregunta
- dejar trazabilidad suficiente para separar fallo de planner, linking y sintesis

## Estado tras T19

El orquestador opera sobre el snapshot linked y hereda:
- planner compartido
- sintesis compartida
- lexicalizacion multilingue ES/EN
- consolidacion canonica previa
- enrichment residual de linking y value surfaces
- link completion residual restringido a las familias reales detectadas en sandbox
- trazabilidad mas clara entre fallo de consulta, fallo estructural y fallo de surface rendering

## Uso con preguntas nuevas

Para depurar primero planner y boundedness, usa `query_workbench.py`.
Cuando quieras ver un lote completo sin `expected_uris`, usa `python src/8_retrieval/qa_sandbox_diagnostic.py`.
Cuando el plan ya sea razonable, usa `semantic_rag.py` para comprobar si la sintesis comparte bien la misma evidencia y la verbaliza con calidad suficiente sobre el grafo linked.

Tras T20, las preguntas equivalentes en espanol e ingles deben converger a la misma familia y la misma SPARQL, cambiando solo el idioma del render final.

Tras T21, esa misma propiedad se comprueba tambien sobre el manual `chunks_8070_quick_ref.txt`: las preguntas ES/EN del quick ref deben resolverse sobre el mismo `abox_linked.ttl`, no sobre un runtime paralelo.
