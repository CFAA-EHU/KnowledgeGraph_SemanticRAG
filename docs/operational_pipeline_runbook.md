# Operational Pipeline Runbook

## Rebuild primario del runtime

El camino operativo primario para reconstruir el runtime aceptado es:

```bash
python run_runtime_clean_rebuild.py --mode resume-compatible
```

Este entrypoint es el contrato principal para:

- rebuild multi-manual del scope aceptado
- validacion del runtime reconstruido
- publicacion opcional en GraphDB

Modos soportados:

- `resume-compatible`
- `force-stale`
- `force-all`

Perfiles de retry soportados:

- `standard`
- `rate-limit-drain`
- `micro-batch-recovery`

El extractor usa fallback entre modelos Mistral configurados. Si un modelo devuelve `429` o agota cuota operativa, el proceso intenta el siguiente modelo compatible antes de declarar fallo del chunk.

## Entrypoint operativo de soporte

`run_operational_pipeline.py` sigue siendo estable, pero no es el camino primario de rebuild completo. Su uso recomendado es:

- rebuild tactico del runtime por defecto
- onboarding de un manual cada vez
- ejecucion operacional de menor alcance

Uso base:

```bash
python run_operational_pipeline.py --mode resume-compatible
```

Onboarding puntual de un manual:

```bash
python run_operational_pipeline.py --source-chunks data/raw/chunks_8070_quick_ref.txt --manual-id 8070_quick_ref --mode resume-compatible
```

## Secuencia del build operativo

El build operativo estable sigue esta cadena:

1. `src/1_ingestion/density_analyzer.py`
2. `src/6_extraction/abox_input_builder.py`
3. `src/6_extraction/abox_extractor.py`
4. `src/6_extraction/abox_merger.py`
5. `src/6_extraction/abox_canonicalizer.py`
6. `src/6_extraction/abox_graph_enricher.py`
7. `src/6_extraction/abox_link_completer.py`
8. `src/8_retrieval/multilingual_lexicon_builder.py`

## Runtime contract

El runtime operativo debe cargar:

- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/multilingual_lexicon.json`

Artefactos estructurales vivos del build:

- `data/processed/abox_input.json`
- `data/processed/abox_merged.ttl`
- `data/processed/abox_canonical.ttl`
- `data/processed/abox_enriched.ttl`
- `data/processed/abox_linked.ttl`

Mapas y reportes estructurales vivos:

- `data/processed/canonical_entity_map.json`
- `data/processed/canonicalization_report.json`
- `data/processed/canonicalization_resolution_candidates.json`
- `data/processed/enrichment_report.json`
- `data/processed/enrichment_link_map.json`
- `data/processed/enrichment_surface_map.json`
- `data/processed/link_completion_report.json`
- `data/processed/link_completion_map.json`
- `data/processed/link_completion_candidates.json`
- `data/processed/graphdb_publication_report.json`

## Politica de `data/processed`

`data/processed` se interpreta en cuatro grupos:

1. `runtime_contract`
2. `accepted_project_operational_artifact`
3. `historical_campaign_traceability`
4. `debug_and_diagnostics`

Regla operativa:

- un rebuild limpio reconstruye `runtime_contract`
- preserva y puede refrescar `accepted_project_operational_artifact`
- no consume `historical_campaign_traceability` como input contractual
- puede sobreescribir `debug_and_diagnostics`

## Frontera del proyecto retenido

El proyecto de referencia brochadora/CNC 8070 sigue retenido dentro de este repo por compatibilidad y validacion, pero su frontera ya debe leerse desde:

- `projects/broaching-cnc-8070/project_scope_manifest.json`
- `data/processed/t27_project_specific_boundary_registry.json`

Estas rutas no reemplazan los paths vivos de `data/raw/`, `data/golden_set/` o `data/processed/*` manual-especifico. Solo hacen explicita la agrupacion canonicamente project-specific mientras el split futuro aun no se ejecuta.

## Consulta manual

El entrypoint principal para consultas manuales es:

```bash
python query_workbench.py "Que directiva cumple la maquina?" --backend rdflib
```

`query_workbench.py` muestra:

- pregunta normalizada
- familia de plan
- boundedness prevista
- evidencia recuperada
- respuesta sintetizada

Usa `embedded_store.py` solo para inspeccion SPARQL directa sin planner ni sintesis.

## GraphDB mirror

GraphDB es el backend espejo del mismo grafo operativo. `rdflib` sigue siendo el backend de referencia y el fallback seguro.

Publicacion:

```bash
python src/7_database/publish_to_graphdb.py
```

Healthcheck:

```bash
python src/7_database/graphdb_healthcheck.py
```

Comparacion basica de equivalencia:

```bash
python src/7_database/graph_store.py
```

Consulta via GraphDB:

```bash
python query_workbench.py "Que directiva cumple la maquina?" --backend graphdb
```

Fallback a RDFLib si GraphDB falla:

```bash
python query_workbench.py "Que directiva cumple la maquina?" --backend rdflib
```

## Evaluacion formal

Entry point oficial:

```bash
python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_canonical.json
```

Gates operativos vigentes del proyecto actual:

- `data/golden_set/QA_canonical.json`
- `data/golden_set/QA_multihop.json`
- `data/golden_set/QA_8070_quick_ref_bilingual_v2.json`
- `data/golden_set/QA_cross.json`

El proyecto actual conserva ademas evaluaciones manual-especificas aceptadas. Esas evaluaciones siguen siendo utiles para el proyecto de referencia, pero no redefinen por si mismas el contrato reusable del core.

## Que no forma parte del camino primario

No deben documentarse como entrypoints operativos normales:

- `history/tooling/campaigns/run_t25_sequential_integration.py`
- `history/tooling/campaigns/run_t25_2_installation_recovery.py`
- `history/tooling/campaigns/run_t26_error_manual_onboarding.py`
- `history/tooling/diagnostics/check_mistral_api_usage.py`
- `history/tooling/runtime_clean_rebuild_plan.md`
- `misc/coding-team/repo-reusability-core-split/`

Si se invocan los shims de compatibilidad que siguen en la raiz, deben entenderse solo como redirects historicos y nunca como el camino preferido del runtime.

Tampoco forman parte del runtime por defecto:

- `src/2_extraction/`
- `src/3_merging/`
- `src/5_alignment/`
