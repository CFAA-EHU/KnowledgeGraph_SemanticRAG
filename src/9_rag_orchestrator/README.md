# src/9_rag_orchestrator

Capa conversacional final del Semantic RAG operativo.

## Script principal

### `semantic_rag.py`
Consume:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_merged.ttl`
- `data/processed/schema_condensed.txt`
- el planner compartido de `src/8_retrieval/text_to_sparql.py`

Responsabilidades:
- recibir la pregunta del usuario
- construir y ejecutar el mismo `QueryPlan` compartido que usa el evaluador
- mostrar familia, confianza, boundedness y accion recomendada
- sintetizar una respuesta final sobre el contexto recuperado

## Estado tras T13

El orquestador ya no depende solo de familias multi-hop benchmarkeadas. Ahora tambien aprovecha:
- familias generalizadas fuera del benchmark
- normalizacion de anclas
- boundedness final del plan
- pruning por paso cuando aplica
- senal explicita de `recommended_action`

Eso permite distinguir mejor:
- fallo de planner/generalizacion
- fallo de boundedness
- fallo de sintesis

## Uso con preguntas nuevas

Para depurar primero el planner, usa `query_workbench.py`.
Cuando el plan ya sea razonable, usa `semantic_rag.py` para comprobar si la sintesis introduce ruido adicional.

## Siguiente cuello de botella

Tras T13, el planner deja de ser el limite principal del runtime actual. Lo siguiente a mejorar aqui es:
- sintesis final mas natural
- mejor renderizado de identificadores, direcciones y valores literales
