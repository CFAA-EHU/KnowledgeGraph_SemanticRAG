# src/8_retrieval

Capa de recuperacion SPARQL, evaluacion y sintesis compartida del runtime operativo.

## Contrato de grafo

Planner, evaluacion, sandbox y sintesis operan sobre:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/multilingual_lexicon.json`

Los snapshots `abox_merged.ttl`, `abox_canonical.ttl` y `abox_enriched.ttl` solo se usan para comparaciones estructurales o diagnostico controlado.

`schema_condensed.txt` se regenera desde `ontology_aligned.ttl` y debe mantenerse alineado cuando cambian axiomas de T-Box como `rdfs:subClassOf`, `rdfs:domain`, `rdfs:range` u `owl:disjointWith`.

## Componentes principales

### `text_to_sparql.py`
Fuente unica de planificacion de consulta.

Tras T20:
- detecta idioma de la pregunta
- normaliza preguntas ES/EN al mismo plan canonico
- expone `question_language`, `normalized_question` y `multilingual_lexicon_hits`

Tras T22:
- aplica prioridad estricta `cross_manual_strict -> quick_ref_strict -> A218 consolidado -> generalizado`
- usa `planner_generalization_catalog_v2.json` como catalogo quick-ref cerrado al benchmark `QA_8070_quick_ref_bilingual_v2.json`
- usa `cross_plan_catalog.json` como catalogo cross-manual minimo cerrado a `QA_cross.json`
- estabiliza familia, ancla y firma SPARQL por par ES/EN antes de caer en fallbacks

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

Este modulo no cambia URIs ni traduce el RDF. Solo construye soporte lexical para normalizacion y planificacion multilingue.

### `schema_condenser.py`
Genera `data/processed/schema_condensed.txt` a partir de la T-Box operativa.

Debe ejecutarse despues de cambios en `ontology_aligned.ttl`, especialmente tras enriquecimientos C13. El schema condensado es insumo del planner y de la sintesis, por lo que no debe quedar obsoleto respecto a la T-Box publicada.

### `qa_evaluator.py`
Evalua el runtime formal sobre:
- `data/golden_set/QA_canonical.json`
- `data/golden_set/QA_multihop.json`
- `data/golden_set/QA_bilingual.json`
- `data/golden_set/QA_8070_quick_ref_bilingual.json`

La corrida canonica actual se persiste en `data/processed/generalization_eval_report.json` y la multi-hop en `data/processed/multihop_eval_report.json`.
La convergencia bilingue se persiste en:
- `data/processed/bilingual_eval_report.json`
- `data/processed/bilingual_debug_report.json`
- `data/processed/bilingual_decision_report.json`
- `data/processed/quick_ref_bilingual_eval_report.json`
- `data/processed/quick_ref_bilingual_debug_report.json`
- `data/processed/quick_ref_integration_decision_report.json`
- `data/processed/quick_ref_v2_planner_alignment_report.json`
- `data/processed/cross_planner_alignment_report.json`
- `data/processed/t22_planner_eval_report.json`
- `data/processed/t22_planner_decision_report.json`

Uso principal:
- benchmark formal
- gates bilingues y cross ya estabilizados
- comparacion contra datasets contractuales

### `qa_sandbox_diagnostic.py`
Ejecuta `QA_sandbox.json` como lote de diagnostico estructural usando el pipeline real.

Por defecto corre contra `abox_linked.ttl`, pero puede compararse contra snapshots anteriores con:

```bash
python src/8_retrieval/qa_sandbox_diagnostic.py --abox-file data/processed/abox_enriched.ttl
python src/8_retrieval/qa_sandbox_diagnostic.py --abox-file data/processed/abox_canonical.ttl
python src/8_retrieval/qa_sandbox_diagnostic.py --abox-file data/processed/abox_merged.ttl
```

Uso principal:
- diagnostico estructural
- comparacion entre snapshots del grafo
- analisis fuera del benchmark formal

## Estado tras T19

- `QA_canonical` estable en `13/13`
- `QA_multihop` estable en `7/7`
- `QA_bilingual` valida convergencia ES/EN sobre el mismo grafo
- `QA_8070_quick_ref_bilingual` valida el primer onboarding real de un manual nuevo en ingles sobre el mismo grafo
- planner y sintesis operan sobre un grafo canonico, enriquecido, linked y lexicalizado en ES/EN
- T16-T20 separan benchmark formal, sandbox batch, consolidacion, enrichment, link completion residual y soporte bilingue
- el residuo principal ya no es deuda canonica amplia, sino un follow-up pequeno de seleccion de evidencia y surface rendering sobre el grafo linked

## Estado tras T22

- el catalogo quick-ref soportado ya cubre las 19 familias reales del gate `QA_8070_quick_ref_bilingual_v2.json`
- el catalogo cross soportado ya cubre las 11 familias reales del gate `QA_cross.json`
- la convergencia exigida por familia y firma SPARQL queda estabilizada en los dos benchmarks:
  - quick-ref v2: `20/20`
  - cross-manual: `11/11`
- el planner ya no debe degradar a familias genericas cuando existe una familia quick-ref o cross con evidencia positiva del catalogo

## Estado tras estabilizacion A-Box/T-Box y C13

El runtime actual se evalua sobre un grafo final saneado:

- `abox_linked.ttl` no contiene hard failures semanticos
- `ontology_aligned.ttl` incluye axiomas T-Box seguros y evidenciados
- `schema_condensed.txt` esta regenerado desde esa T-Box
- GraphDB esta publicado como espejo del mismo runtime

Estado de gates tras la estabilizacion:

- `QA_canonical`: `13/13`
- `QA_multihop`: `7/7`
- `QA_chunks_8070_installation_manual`: `15/15`
- `QA_chunks_man_8070_err`: `15/15`
- `QA_8070_quick_ref_bilingual_v2`: sin benchmark runner blockers
- `QA_cross`: sin benchmark runner blockers

Quick-ref v2 y cross siguen teniendo casos de alineacion no perfecta en sus decision reports; se consideran operativos sin blocker, no gates completamente solidos.

## Regresion y diagnostico

Antes de cerrar cambios en esta capa, ejecutar segun el objetivo del cambio:
- benchmark formal: `python src/8_retrieval/qa_evaluator.py`
- benchmark multi-hop: `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json`
- benchmark bilingue: `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_bilingual.json`
- benchmark bilingue quick ref: `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_8070_quick_ref_bilingual.json`
- gate quick-ref v2: `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_8070_quick_ref_bilingual_v2.json --report-path data/processed/quick_ref_v2_eval_report.json --debug-report-path data/processed/quick_ref_v2_debug_report.json`
- gate cross-manual: `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_cross.json --report-path data/processed/cross_eval_report.json --debug-report-path data/processed/cross_debug_report.json`
- sandbox batch: `python src/8_retrieval/qa_sandbox_diagnostic.py`
- preguntas nuevas interactivas: `python query_workbench.py "?Cual es el correo electronico de contacto de EKIN indicado en el manual?" --with-synthesis`

Si el cambio toca T-Box o schema:

```bash
python src/8_retrieval/schema_condenser.py
python src/6_extraction/abox_semantic_validator.py --abox-path data/processed/abox_linked.ttl
python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_canonical.json
python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json
```

## Entry points dentro del modulo

- benchmark formal principal: `qa_evaluator.py`
- sandbox diagnostico: `qa_sandbox_diagnostic.py`
- pregunta manual con plan y backend: `query_workbench.py`
