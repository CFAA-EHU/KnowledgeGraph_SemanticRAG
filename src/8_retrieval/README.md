# src/8_retrieval

Capa de recuperacion SPARQL, evaluacion y sintesis compartida del runtime operativo.

## Contrato de grafo

Planner, evaluacion, sandbox y sintesis operan sobre:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_linked.ttl`

Los snapshots `abox_merged.ttl`, `abox_canonical.ttl` y `abox_enriched.ttl` solo se usan para comparaciones estructurales o diagnostico controlado.

## Componentes principales

### `text_to_sparql.py`
Fuente unica de planificacion de consulta.

### `synthesis_pipeline.py`
Capa compartida de post-retrieval y sintesis.

### `qa_evaluator.py`
Evalua el runtime formal sobre:
- `data/golden_set/QA_canonical.json`
- `data/golden_set/QA_multihop.json`

La corrida canonica actual se persiste en `data/processed/generalization_eval_report.json` y la multi-hop en `data/processed/multihop_eval_report.json`.

### `qa_sandbox_diagnostic.py`
Ejecuta `QA_sandbox.json` como lote de diagnostico estructural usando el pipeline real.

Por defecto corre contra `abox_linked.ttl`, pero puede compararse contra snapshots anteriores con:

```bash
python src/8_retrieval/qa_sandbox_diagnostic.py --abox-file data/processed/abox_enriched.ttl
python src/8_retrieval/qa_sandbox_diagnostic.py --abox-file data/processed/abox_canonical.ttl
python src/8_retrieval/qa_sandbox_diagnostic.py --abox-file data/processed/abox_merged.ttl
```

## Estado tras T19

- `QA_canonical` estable en `13/13`
- `QA_multihop` estable en `7/7`
- planner y sintesis operan sobre un grafo canonico, enriquecido y linked
- T16-T19 separan benchmark formal, sandbox batch, consolidacion, enrichment y link completion residual
- el residuo principal ya no es deuda canonica amplia, sino un follow-up pequeno de seleccion de evidencia y surface rendering sobre el grafo linked

## Regresion y diagnostico

Antes de cerrar cambios en esta capa, ejecutar segun el objetivo del cambio:
- benchmark formal: `python src/8_retrieval/qa_evaluator.py`
- benchmark multi-hop: `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json`
- sandbox batch: `python src/8_retrieval/qa_sandbox_diagnostic.py`
- preguntas nuevas interactivas: `python query_workbench.py "?Cual es el correo electronico de contacto de EKIN indicado en el manual?" --with-synthesis`
