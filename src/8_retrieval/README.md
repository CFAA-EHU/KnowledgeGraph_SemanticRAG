# src/8_retrieval

Capa de recuperacion SPARQL, evaluacion y sintesis compartida del runtime operativo.

## Contrato de grafo

Planner, evaluacion, sandbox y sintesis operan sobre:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_enriched.ttl`

El snapshot bruto `abox_merged.ttl` y el snapshot canonico `abox_canonical.ttl` solo se usan para comparaciones estructurales o diagnostico controlado.

## Componentes principales

### `text_to_sparql.py`
Fuente unica de planificacion de consulta.

### `synthesis_pipeline.py`
Capa compartida de post-retrieval y sintesis.

### `qa_evaluator.py`
Evalua el runtime formal sobre:
- `data/golden_set/QA_canonical.json`
- `data/golden_set/QA_multihop.json`

### `qa_sandbox_diagnostic.py`
Ejecuta `QA_sandbox.json` como lote de diagnostico estructural usando el pipeline real.

Por defecto corre contra `abox_enriched.ttl`, pero puede compararse contra snapshots anteriores con:

```bash
python src/8_retrieval/qa_sandbox_diagnostic.py --abox-file data/processed/abox_canonical.ttl
python src/8_retrieval/qa_sandbox_diagnostic.py --abox-file data/processed/abox_merged.ttl
```

## Estado tras T18

- `QA_canonical` estable en `13/13`
- `QA_multihop` estable en `7/7`
- planner y sintesis operan sobre un grafo canonico y enriquecido
- T16-T18 separan benchmark formal, sandbox batch, consolidacion y enrichment residual
- el residuo principal ya no es deuda canonica amplia, sino linking selectivo en sandbox

## Regresion y diagnostico

Antes de cerrar cambios en esta capa, ejecutar segun el objetivo del cambio:
- benchmark formal: `python src/8_retrieval/qa_evaluator.py`
- benchmark multi-hop: `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json`
- sandbox batch: `python src/8_retrieval/qa_sandbox_diagnostic.py`
- preguntas nuevas interactivas: `python query_workbench.py "?Cual es el correo electronico de contacto de EKIN indicado en el manual?" --with-synthesis`
