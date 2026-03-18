# src/9_rag_orchestrator — Orquestación final del Semantic RAG

Este directorio contiene la capa de respuesta final al usuario sobre el runtime operativo.

## Script principal

### `semantic_rag.py`
Consume:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_merged.ttl`
- el query layer compartido de `src/8_retrieval/text_to_sparql.py`

Responsabilidades:
- interpretar la pregunta del usuario
- invocar el planner compartido
- ejecutar las consultas SPARQL resultantes
- sintetizar una respuesta final a partir de los resultados

---

## Estado actual tras T12

El orquestador ya no usa una lógica de consulta separada del evaluador.

Ahora comparte:
- intención detectada
- ancla detectada
- familia de plan
- profundidad prevista
- ejecución por pasos
- boundedness por salto
- fallback controlado

Eso significa que las diferencias entre evaluación y runtime conversacional ya no vienen de dos generadores de consulta distintos, sino principalmente de:
- generalización del planner
- boundedness residual
- síntesis final

---

## Qué soporta ahora

El runtime conversacional ya puede trabajar con:
- preguntas de `1` hop
- preguntas de `2` hops
- preguntas de `3` hops dentro de las familias multi-hop benchmarkeadas

Las familias multi-hop validadas en T12 incluyen rutas como:
- `Machine -> cumpleNormativa -> Directive`
- `Manual <- ilustradoEn -> Figure`
- `SistemaSeguridadMaquina -> requiereMantenimiento -> PlanMantenimientoEKIN`
- `Columna_46 -> tieneComponente -> CarroPortaPiezas_46 -> controla -> ReglaLineal_46_1`

---

## Qué comprobar aquí

Este módulo se usa para comprobar:
- calidad de la respuesta final al usuario
- si la síntesis introduce errores adicionales
- si el planner compartido mantiene su comportamiento dentro del flujo conversacional

No se usa para demostrar queryability del grafo. Para eso existen:
- la suite SPARQL canónica
- el benchmark multi-hop
- `query_workbench.py`

---

## Relación con otras piezas

- `src/7_database/embedded_store.py` aporta el grafo en memoria
- `src/8_retrieval/text_to_sparql.py` aporta el planner compartido
- `src/8_retrieval/qa_evaluator.py` mide el comportamiento
- `query_workbench.py` permite probar preguntas nuevas y depurar consultas por pasos

---

## Limitación actual

Tras T12, el grafo y el planner ya soportan multi-hop benchmarkeado de forma fiable.

El siguiente cuello de botella aquí ya no es soporte multi-hop básico, sino:
- generalizar el planner fuera de las familias seedadas
- mejorar boundedness en preguntas no benchmark
- y, solo después, seguir afinando la síntesis final si hiciera falta