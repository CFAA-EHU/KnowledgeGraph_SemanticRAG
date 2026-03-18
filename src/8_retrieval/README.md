# src/8_retrieval

Capa de recuperacion SPARQL, evaluacion y sintesis compartida del runtime operativo.

## Componentes principales

### `schema_condenser.py`
Genera `data/processed/schema_condensed.txt` a partir de `data/processed/ontology_aligned.ttl`.

### `text_to_sparql.py`
Sigue siendo la fuente unica de planificacion de consulta del proyecto.

Responsabilidades actuales:
- parsing determinista de intencion
- normalizacion de anclas y variantes lexicas
- seleccion de familias benchmarkeadas y generalizadas
- construccion de `QueryPlan` por pasos
- soporte de 1, 2 y 3 hops
- propagacion de candidatos entre saltos
- boundedness por familia y por paso
- confianza del plan y accion recomendada
- fallback controlado
- export de catalogos y matriz de boundedness

### `synthesis_pipeline.py`
Capa compartida de post-retrieval y sintesis estabilizada en T14-T15.

Responsabilidades:
- ranking de evidencia recuperada
- seleccion de filas candidatas para respuesta
- normalizacion determinista de valores
- renderizado final de respuesta
- pulido superficial compacto y trazable
- trazabilidad de evidencia cruda, evidencia elegida y valores normalizados

Artefactos que exporta o alimenta:
- `data/processed/value_normalization_rules.json`
- `data/processed/surface_rendering_rules.json`
- `data/processed/synthesis_debug_report.json`
- `data/processed/synthesis_eval_report.json`
- `data/processed/surface_polish_eval_report.json`
- `data/processed/surface_polish_decision_report.json`

### `qa_evaluator.py`
Evalua el runtime operativo sobre:
- `data/golden_set/QA_canonical.json`
- `data/golden_set/QA_multihop.json`

Ahora persiste tanto retrieval como sintesis:
- `data/processed/generalization_eval_report.json`
- `data/processed/qa_failure_analysis.json`
- `data/processed/multihop_eval_report.json`
- `data/processed/query_debug_report.json`
- `data/processed/synthesis_debug_report.json`
- `data/processed/synthesis_eval_report.json`
- `data/processed/synthesis_decision_report.json`

## Estado tras T15

### Lo ya conseguido
- planner multi-hop compartido estable
- `QA_multihop` conservado en `7/7`
- `QA_canonical` conservado en `13/13`
- ranking post-retrieval y seleccion de evidencia compartidos
- normalizacion explicita de correo, direccion, directiva y figura
- pulido superficial final auditable antes y despues del render
- separacion trazable entre evidencia recuperada, evidencia seleccionada y respuesta final

### Lo que sigue pendiente
En esta capa ya no queda un cuello de botella estructural para A218. Lo pendiente es menor y no justifica otra refactorizacion grande:
- micro-pulido ocasional de superficie en respuestas largas
- abrir la siguiente capacidad del sistema en vez de seguir optimizando el mismo caso

## Regresion obligatoria

Antes de cerrar cambios en esta capa, ejecutar al menos:
- `python src/8_retrieval/qa_evaluator.py`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json`
- `python query_workbench.py "¿Cuál es el correo electrónico de contacto de EKIN indicado en el manual?" --with-synthesis`
- `python query_workbench.py "¿Dónde se encuentra la dirección de la empresa EKIN mencionada en el manual?" --with-synthesis`
