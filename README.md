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

## Entrypoints oficiales

Pipeline operativo:
- `python run_operational_pipeline.py --mode resume-compatible`

Onboarding piloto de un manual nuevo:
- `python run_operational_pipeline.py --source-chunks data/raw/chunks_8070_quick_ref.txt --manual-id 8070_quick_ref --mode resume-compatible`

Pregunta manual con plan, backend y trazas:
- `python query_workbench.py "¿Qué directiva cumple la máquina?" --backend rdflib`
- `python query_workbench.py "¿Qué directiva cumple la máquina?" --backend graphdb`

Benchmark formal:
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_canonical.json`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json`

Sandbox diagnóstico:
- `python src/8_retrieval/qa_sandbox_diagnostic.py`

Publicación a GraphDB:
- `python src/7_database/publish_to_graphdb.py`

Healthcheck GraphDB:
- `python src/7_database/graphdb_healthcheck.py`

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

Tras T23, el runtime mantiene dos backends de consulta:
- `rdflib` en memoria como backend de referencia y por defecto
- `GraphDB` como backend espejo opcional del mismo grafo operativo

Regla operativa:
- `rdflib` sigue siendo el backend de referencia
- GraphDB se usa como backend espejo para publicacion, verificacion, consulta remota y smoke tests
- el planner y la sintesis no cambian por activar GraphDB

Scripts nuevos de T23:
- `src/7_database/graphdb_client.py`
- `src/7_database/graph_store.py`
- `src/7_database/publish_to_graphdb.py`
- `src/7_database/graphdb_healthcheck.py`

Artefactos nuevos de T23:
- `data/processed/graphdb_publication_report.json`
- `data/processed/graphdb_equivalence_report.json`
- `data/processed/t23_graphdb_decision_report.json`

Eso deja separadas cuatro capas:
- `abox_merged.ttl`: snapshot bruto post-merge para diagnostico
- `abox_canonical.ttl`: snapshot canonico intermedio para consolidacion estructural
- `abox_enriched.ttl`: snapshot enriquecido intermedio para linking y value surfaces genericos
- `abox_linked.ttl`: snapshot operativo final con link completion residual de alta confianza
- `multilingual_lexicon.json`: lexicalizacion bilingue ES/EN sobre el mismo snapshot operativo final

## Estado operativo consolidado

- el grafo sigue siendo unico y canonico; no se duplica por idioma
- `textoExtracto` conserva idioma original
- el planner converge en los benchmarks estabilizados de A218, quick-ref y cross-manual
- el baseline actual se mantiene en:
  - `QA_canonical = 13/13`
  - `QA_multihop = 7/7`
- GraphDB ya puede reflejar el mismo grafo operativo como backend espejo

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

Desde T23 admite:
- `--backend rdflib`
- `--backend graphdb`

La planificacion sigue ocurriendo sobre el grafo local de referencia; el selector de backend solo cambia la ejecucion SPARQL del mismo runtime operativo.

## Fuente unica de verdad

Las rutas y artefactos compartidos viven en `artifact_contracts.py`.
