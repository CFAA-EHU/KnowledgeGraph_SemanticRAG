# src/9_rag_orchestrator — Orquestación final del Semantic RAG

Este directorio contiene la capa de respuesta final al usuario sobre el runtime operativo.

## Script principal

### `semantic_rag.py`
Consume:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_merged.ttl`
- el query layer compartido en `src/8_retrieval/text_to_sparql.py`

Responsabilidades:
- interpretar la pregunta del usuario
- invocar el planner/QueryPlan compartido
- ejecutar las consultas SPARQL resultantes
- sintetizar una respuesta final a partir de los resultados

## Estado actual
Tras T10, el orquestador ya no usa una lógica de consulta separada del evaluador.  
Comparte el mismo query layer y por eso las diferencias entre evaluación y runtime conversacional ya no vienen de dos generadores distintos.

## Qué comprobar aquí
Este módulo ya no se usa para demostrar queryability del grafo.  
Para eso existen:
- la suite de SPARQL canónicas
- el benchmark multi-hop
- el workbench

El orquestador se usa para comprobar:
- calidad de respuesta final
- robustez conversacional
- si la síntesis introduce fallos adicionales

## Relación con otras piezas
- `src/7_database/embedded_store.py` aporta el grafo en memoria
- `src/8_retrieval/text_to_sparql.py` aporta el planner de consulta
- `src/8_retrieval/qa_evaluator.py` mide el comportamiento
- `query_workbench.py` permite probar preguntas nuevas con trazabilidad

## Limitación actual
El grafo ya soporta rutas multi-hop útiles.  
El siguiente trabajo aquí dependerá de la evolución del planner multi-hop y, después, de la síntesis.