# src/8_retrieval

Capa de recuperacion SPARQL, evaluacion y sintesis compartida del runtime operativo.

## Contrato de grafo

Planner, evaluacion, sandbox y sintesis operan sobre:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/multilingual_lexicon.json`

Los snapshots `abox_merged.ttl`, `abox_canonical.ttl` y `abox_enriched.ttl` solo se usan para comparaciones estructurales o diagnostico controlado.

## Componentes principales

### `text_to_sparql.py`
Fuente unica de planificacion de consulta.

Tras T20:
- detecta idioma de la pregunta
- normaliza preguntas ES/EN al mismo plan canonico
- expone `question_language`, `normalized_question` y `multilingual_lexicon_hits`

### `synthesis_pipeline.py`
Capa compartida de post-retrieval y sintesis.

Tras T20:
- responde en `es` o `en` segun la pregunta
- reutiliza el mismo grafo y la misma evidencia
- no traduce `textoExtracto` completo; re-renderiza surfaces y plantillas

### `multilingual_query_normalizer.py`
Normalizacion bilingue ES/EN previa a `build_query_plan(...)`.

### `multilingual_lexicon_builder.py`
Construye `data/processed/multilingual_lexicon.json` a partir del grafo operativo final, la ontologia y `cache/terms_cache.json`.

### `qa_evaluator.py`
Evalua el runtime formal sobre:
- `data/golden_set/QA_canonical.json`
- `data/golden_set/QA_multihop.json`
- `data/golden_set/QA_bilingual.json`

La corrida canonica actual se persiste en `data/processed/generalization_eval_report.json` y la multi-hop en `data/processed/multihop_eval_report.json`.
La convergencia bilingue se persiste en:
- `data/processed/bilingual_eval_report.json`
- `data/processed/bilingual_debug_report.json`
- `data/processed/bilingual_decision_report.json`

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
- `QA_bilingual` valida convergencia ES/EN sobre el mismo grafo
- planner y sintesis operan sobre un grafo canonico, enriquecido, linked y lexicalizado en ES/EN
- T16-T20 separan benchmark formal, sandbox batch, consolidacion, enrichment, link completion residual y soporte bilingue
- el residuo principal ya no es deuda canonica amplia, sino un follow-up pequeno de seleccion de evidencia y surface rendering sobre el grafo linked

## Regresion y diagnostico

Antes de cerrar cambios en esta capa, ejecutar segun el objetivo del cambio:
- benchmark formal: `python src/8_retrieval/qa_evaluator.py`
- benchmark multi-hop: `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json`
- benchmark bilingue: `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_bilingual.json`
- sandbox batch: `python src/8_retrieval/qa_sandbox_diagnostic.py`
- preguntas nuevas interactivas: `python query_workbench.py "?Cual es el correo electronico de contacto de EKIN indicado en el manual?" --with-synthesis`
