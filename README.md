# KnowledgeGraph_SemanticRAG

Pipeline operativo y experimental para convertir manuales tecnicos industriales en un knowledge graph RDF/OWL consultable con SPARQL y reutilizable en un Semantic RAG trazable.

El caso operativo consolidado sigue siendo el manual de la brochadora electromecanica A218 / RASHEM - 7x3000x500.

## Carriles del repositorio

### Carril operativo
Es el camino oficial de build, consulta y evaluacion.

Artefactos operativos clave:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_input.json`
- `data/processed/abox_merged.ttl` como snapshot bruto post-merge
- `data/processed/abox_canonical.ttl` como snapshot canonico intermedio
- `data/processed/abox_enriched.ttl` como snapshot enriquecido intermedio
- `data/processed/abox_linked.ttl` como A-Box operativa final del runtime
- `data/processed/multilingual_lexicon.json` como lexicalizacion ES/EN sobre el mismo grafo canonico
- `data/processed/language_detection_report.json`
- `data/processed/canonical_entity_map.json`
- `data/processed/canonicalization_report.json`
- `data/processed/enrichment_report.json`
- `data/processed/enrichment_link_map.json`
- `data/processed/enrichment_surface_map.json`
- `data/processed/link_completion_report.json`
- `data/processed/link_completion_map.json`
- `data/processed/link_completion_candidates.json`
- `data/processed/link_completion_eval_report.json`
- `data/processed/link_completion_decision_report.json`
- `data/processed/schema_condensed.txt`
- `data/golden_set/QA_canonical.json`
- `data/golden_set/QA_multihop.json`
- `data/golden_set/QA_sandbox.json`
- `data/golden_set/QA_bilingual.json`
- `data/golden_set/QA_8070_quick_ref_bilingual.json`
- `data/golden_set/QA_8070_quick_ref_bilingual_v2.json`
- `data/golden_set/QA_cross.json`
- `data/processed/quick_ref_density_report.json`
- `data/processed/quick_ref_abox_input.json`
- `data/processed/quick_ref_onboarding_report.json`
- `data/processed/quick_ref_bilingual_eval_report.json`
- `data/processed/quick_ref_bilingual_debug_report.json`
- `data/processed/quick_ref_integration_decision_report.json`
- `data/processed/quick_ref_v2_eval_report.json`
- `data/processed/quick_ref_v2_debug_report.json`
- `data/processed/quick_ref_v2_planner_alignment_report.json`
- `data/processed/cross_eval_report.json`
- `data/processed/cross_debug_report.json`
- `data/processed/cross_planner_alignment_report.json`
- `data/processed/planner_generalization_catalog_v2.json`
- `data/processed/cross_plan_catalog.json`
- `data/processed/t21_readiness_decision_report.json`
- `data/processed/t22_planner_eval_report.json`
- `data/processed/t22_planner_decision_report.json`

### Carril experimental
Se conserva para exploracion, pero no define el runtime por defecto.

## Build operativo

Entrypoint oficial:
- `python run_operational_pipeline.py --mode resume-compatible`

Onboarding piloto de un manual nuevo en ingles:
- `python run_operational_pipeline.py --source-chunks data/raw/chunks_8070_quick_ref.txt --manual-id 8070_quick_ref --mode resume-compatible`

El flujo operativo completo ejecuta:
- `src/6_extraction/abox_input_builder.py`
- `src/6_extraction/abox_extractor.py`
- `src/6_extraction/abox_merger.py`
- `src/6_extraction/abox_canonicalizer.py`
- `src/6_extraction/abox_graph_enricher.py`
- `src/6_extraction/abox_link_completer.py`
- `src/8_retrieval/multilingual_lexicon_builder.py`

## Runtime operativo actual

Planner, retrieval, evaluacion y orquestacion consumen:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/multilingual_lexicon.json`

Eso deja separadas cuatro capas:
- `abox_merged.ttl`: snapshot bruto post-merge para diagnostico
- `abox_canonical.ttl`: snapshot canonico intermedio para consolidacion estructural
- `abox_enriched.ttl`: snapshot enriquecido intermedio para linking y value surfaces genericos
- `abox_linked.ttl`: snapshot operativo final con link completion residual de alta confianza
- `multilingual_lexicon.json`: lexicalizacion bilingue ES/EN sobre el mismo snapshot operativo final

## Estado tras T20

- el grafo sigue siendo unico y canonico; no se duplica por idioma
- onboarding marca `source_language` y `language_confidence` por chunk
- `textoExtracto` conserva el idioma original del fragmento
- el planner normaliza preguntas ES/EN al mismo plan canonico
- la sintesis responde en el idioma de la pregunta
- `QA_bilingual` valida convergencia ES/EN sin contaminar `QA_canonical` ni `QA_multihop`

## Estado tras T21

- existe un carril piloto reproducible para onboarding real de un manual nuevo con artefactos `quick_ref_*`
- `chunks_8070_quick_ref.txt` reutiliza el mismo pipeline, el mismo grafo operativo y el mismo planner bilingue
- `QA_8070_quick_ref_bilingual.json` valida convergencia ES/EN especifica del quick ref
- `QA_8070_quick_ref_bilingual_v2.json` actua como gate ampliado de solidez del quick ref ya integrado
- `QA_cross.json` actua como gate separado de integracion semantica cross-manual A218 + 8070
- si faltan credenciales de extraccion, el pipeline deja `quick_ref_density_report.json`, `quick_ref_abox_input.json` y `quick_ref_onboarding_report.json` antes de bloquearse
- la decision operativa del piloto queda en `quick_ref_integration_decision_report.json`
- la decision de readiness antes de limpieza o siguiente manual queda en `t21_readiness_decision_report.json`

## Estado tras T22

- el planner usa un catalogo estricto quick-ref y un catalogo cross-manual minimo, sin duplicar arquitectura ni tocar el grafo
- la prioridad efectiva de planning queda en:
  - `cross_manual_strict`
  - `quick_ref_strict`
  - familias A218 ya consolidadas
  - generalizadas y fallbacks genericos
- `quick_ref_v2` queda en convergencia total operativa:
  - `same_plan_family = 20/20`
  - `same_sparql_signature = 20/20`
  - `pair_ok = 20/20`
  - `answer_language_ok = 20/20`
- `QA_cross` queda tambien en convergencia total operativa:
  - `pair_alignment_ok = 11/11`
  - `cross_case_ok = 11/11`
  - `answer_language_ok = 11/11`
- el baseline se mantiene:
  - `QA_canonical = 13/13`
  - `QA_multihop = 7/7`
- los artefactos que gobiernan el readiness post-planner son:
  - `planner_generalization_catalog_v2.json`
  - `cross_plan_catalog.json`
  - `quick_ref_v2_planner_alignment_report.json`
  - `cross_planner_alignment_report.json`
  - `t22_planner_eval_report.json`
  - `t22_planner_decision_report.json`

## Estado tras T19

- `QA_canonical` se mantiene en `13/13`
- `QA_multihop` se mantiene en `7/7`
- T17 resolvio la deuda canonica dominante
- T18 anadio enrichment residual de linking y value surfaces sobre el grafo canonico
- T19 materializa link completion residual solo para familias observadas en T18
- la whitelist de T19 queda cerrada a cinco familias activas y dos familias bloqueadas con motivo explicito
- el residuo principal deja de justificar otra fase estructural amplia y pasa mas hacia seleccion de evidencia y surface rendering

## Sandbox diagnostico

`QA_sandbox.json` se usa como lote de diagnostico estructural, no como benchmark formal.

`QA_bilingual.json` se usa como sandbox formal bilingue de convergencia ES/EN:
- misma intencion
- misma ancla canonica
- misma familia de plan
- misma SPARQL
- respuesta en el idioma de la pregunta

Runner batch:
- `python src/8_retrieval/qa_sandbox_diagnostic.py`

Artefactos principales de T16-T19:
- `data/processed/sandbox_diagnostic_report.json`
- `data/processed/sandbox_structural_gap_summary.json`
- `data/processed/sandbox_entity_resolution_candidates.json`
- `data/processed/sandbox_promotion_candidates.json`
- `data/processed/sandbox_decision_report.json`
- `data/processed/canonicalization_eval_report.json`
- `data/processed/canonicalization_decision_report.json`
- `data/processed/enrichment_eval_report.json`
- `data/processed/enrichment_decision_report.json`
- `data/processed/link_completion_eval_report.json`
- `data/processed/link_completion_decision_report.json`

## Workbench

`query_workbench.py` sirve para probar preguntas nuevas y ver:
- intencion y ancla detectadas
- idioma detectado y pregunta normalizada
- familia y profundidad previstas
- boundedness por paso y final
- evidencia recuperada
- evidencia seleccionada para sintesis
- respuesta final en el idioma de la pregunta sobre el mismo grafo linked

## Fuente unica de verdad

Las rutas y artefactos compartidos viven en `artifact_contracts.py`.
