# src/9_rag_orchestrator

Capa conversacional final del Semantic RAG operativo.

## Script principal

### `semantic_rag.py`
Consume:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_merged.ttl`
- `data/processed/schema_condensed.txt`
- el planner compartido de `src/8_retrieval/text_to_sparql.py`
- la sintesis compartida de `src/8_retrieval/synthesis_pipeline.py`

Responsabilidades:
- recibir la pregunta del usuario
- construir y ejecutar el mismo `QueryPlan` compartido que usa el evaluador
- mostrar familia, confianza, boundedness y accion recomendada
- ejecutar la sintesis explicita en tres fases logicas:
  - seleccion de evidencia
  - normalizacion de valores
  - renderizado de respuesta
- dejar trazabilidad suficiente para separar fallo de planner y fallo de sintesis

## Estado tras T14

El orquestador ya no depende de una fase final opaca. Ahora aprovecha:
- ranking post-retrieval compartido
- normalizacion de correo, direccion, directiva y otras superficies frecuentes
- trazabilidad de evidencia seleccionada y valores normalizados
- diagnostico mas claro cuando la respuesta es debil o demasiado larga

Eso permite distinguir mejor:
- fallo de planner/generalizacion
- fallo de boundedness
- fallo de seleccion de evidencia
- fallo de normalizacion/renderizado

## Uso con preguntas nuevas

Para depurar primero planner y boundedness, usa `query_workbench.py`.
Cuando el plan ya sea razonable, usa `semantic_rag.py` para comprobar si la sintesis comparte bien la misma evidencia y la verbaliza con calidad suficiente.

## Siguiente cuello de botella

Tras T14, el planner deja de ser el limite principal del runtime actual. Lo siguiente a mejorar aqui es:
- pulido fino de respuestas largas o demasiado literales
- compresion y superficie de salida en casos ya resueltos a nivel de evidencia
