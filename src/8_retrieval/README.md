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
Nueva capa compartida de T14 para post-retrieval.

Responsabilidades:
- ranking de evidencia recuperada
- seleccion de filas candidatas para respuesta
- normalizacion determinista de valores
- renderizado final de respuesta
- trazabilidad de evidencia cruda, evidencia elegida y valores normalizados

Artefactos que exporta o alimenta:
- `data/processed/value_normalization_rules.json`
- `data/processed/synthesis_debug_report.json`
- `data/processed/synthesis_eval_report.json`
- `data/processed/synthesis_decision_report.json`

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

## Estado tras T14

### Lo ya conseguido
- planner multi-hop compartido estable
- `QA_multihop` conservado en `7/7`
- `QA_canonical` conservado en `13/13`
- ranking post-retrieval y seleccion de evidencia compartidos
- normalizacion explicita de correo, direccion, directiva y figura
- separacion trazable entre evidencia recuperada, evidencia seleccionada y respuesta final

### Lo que sigue pendiente
El cuello de botella principal ya no es planner ni boundedness. Lo siguiente a mejorar aqui es:
- pulido fino de superficie en respuestas largas
- compresion de algunas respuestas de proposito/advertencia
- renderizado mas natural en algunos casos limite ya resueltos a nivel de evidencia

## Regresion obligatoria

Antes de cerrar cambios en esta capa, ejecutar al menos:
- `python src/8_retrieval/qa_evaluator.py`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json`
- `python query_workbench.py "¿Cuál es el correo electrónico de contacto de EKIN indicado en el manual?" --with-synthesis`
- `python query_workbench.py "¿Dónde se encuentra la dirección de la empresa EKIN mencionada en el manual?" --with-synthesis`
