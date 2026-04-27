# SemanticRAG

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)
![GraphDB](https://img.shields.io/badge/GraphDB-Semantic_Graph-orange?logo=databricks&logoColor=white)
![Mistral AI](https://img.shields.io/badge/Mistral_AI-LLM_Engine-black?logo=mistral&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

SemanticRAG es un framework para construir runtimes semanticos operativos a partir de manuales tecnicos. El repositorio cubre la ingesta, la extraccion A-Box, la consolidacion estructural del grafo, el soporte multilingue, la publicacion en GraphDB y la evaluacion funcional del runtime resultante.

El repositorio conserva un proyecto activo de referencia basado en manuales de una brochadora y del CNC 8070. Ese corpus, sus golden sets y parte del ajuste de retrieval siguen viviendo aqui por compatibilidad y rebuildabilidad, pero deben entenderse como adjuntos `project-specific`, no como definicion del core reusable.

## Que es reusable core

El nucleo reusable del repositorio incluye:

- ingesta y analisis de densidad en `src/1_ingestion/`
- construccion operativa de A-Box en `src/6_extraction/`
- backend RDF local y mirror GraphDB en `src/7_database/`
- soporte general de retrieval, evaluacion y consulta en `src/8_retrieval/`
- contratos de artefactos y runbooks operativos en `artifact_contracts.py` y `docs/`

Ese core permite reconstruir, publicar, consultar y validar un runtime semantico sin depender conceptualmente del dominio brochadora/8070.

## Que es project-specific

En el estado actual del repositorio siguen siendo especificos del proyecto de referencia:

- `data/raw/`
- `data/golden_set/`
- `cache/terms_cache.json`
- los manuales aceptados A218, 8070 quick-ref, 8070 installation y `man_8070_err`
- los artefactos manual-especificos en `data/processed/a218_*`, `quick_ref_*`, `installation_manual_*`, `8070_installation_*` y `man_8070_err_*`
- parte del tuning del planner y la sintesis en:
  - `src/8_retrieval/text_to_sparql.py`
  - `src/8_retrieval/multilingual_query_normalizer.py`
  - `src/8_retrieval/synthesis_pipeline.py`

Estos elementos se mantienen para soportar el runtime actual y preparar una futura separacion del caso de uso a otro repositorio.

## Area canonica del proyecto de referencia

La frontera project-specific ya no queda solo implicita en `data/raw/`, `data/golden_set/` y los artefactos manual-especificos. El repositorio expone ahora un area canonica para el proyecto retenido:

- `projects/broaching-cnc-8070/`

Esa area no sustituye las rutas vivas actuales. Su funcion es:

- hacer visible el perimetro del proyecto de referencia
- apuntar al manifiesto contractual del caso de uso retenido
- preparar el futuro split a un repositorio propio sin romper el rebuild actual

Manifest principal del proyecto retenido:

- `projects/broaching-cnc-8070/project_scope_manifest.json`

## Entrypoints oficiales

El contrato operativo estable del repositorio queda asi:

### Rebuild primario del runtime

```bash
python run_runtime_clean_rebuild.py --mode resume-compatible
```

Este es el unico entrypoint documentado como camino primario para reconstruir el runtime aceptado de extremo a extremo.

### Entrypoint operativo de soporte

```bash
python run_operational_pipeline.py --mode resume-compatible
```

`run_operational_pipeline.py` sigue siendo un script estable, pero su ambito es mas tactico: rebuild por defecto de menor alcance y onboarding de un manual cada vez.

Ejemplo de onboarding manual:

```bash
python run_operational_pipeline.py --source-chunks data/raw/chunks_8070_quick_ref.txt --manual-id 8070_quick_ref --mode resume-compatible
```

### Publicacion y salud de GraphDB

```bash
python src/7_database/publish_to_graphdb.py
python src/7_database/graphdb_healthcheck.py
```

### Evaluacion formal

```bash
python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_canonical.json
python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json
python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_8070_quick_ref_bilingual_v2.json
python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_cross.json
```

### Consulta manual

```bash
python query_workbench.py "Que directiva cumple la maquina?" --backend rdflib
```

## Runtime contract vivo

El runtime operativo consume y publica estos artefactos vivos:

- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_input.json`
- `data/processed/abox_merged.ttl`
- `data/processed/abox_canonical.ttl`
- `data/processed/abox_enriched.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/multilingual_lexicon.json`

Tambien forman parte del contrato operativo los reportes y mapas estructurales:

- `data/processed/canonical_entity_map.json`
- `data/processed/canonicalization_report.json`
- `data/processed/canonicalization_resolution_candidates.json`
- `data/processed/enrichment_report.json`
- `data/processed/enrichment_link_map.json`
- `data/processed/enrichment_surface_map.json`
- `data/processed/link_completion_report.json`
- `data/processed/link_completion_map.json`
- `data/processed/link_completion_candidates.json`
- `data/processed/abox_semantic_audit.json`
- `data/processed/abox_minted_entity_registry.json`
- `data/processed/abox_merger_rejected_chunks.json`
- `data/processed/t_tbox_enrichment_evidence.json`
- `data/processed/schema_condensed.txt`
- `data/processed/graphdb_publication_report.json`

Los gates operativos vigentes del proyecto actual siguen siendo:

- `data/processed/generalization_eval_report.json`
- `data/processed/multihop_eval_report.json`
- `data/processed/quick_ref_v2_eval_report.json`
- `data/processed/cross_eval_report.json`

## Politica de `data/processed`

`data/processed` no debe interpretarse como un espacio plano donde todos los JSON tienen el mismo estatus. Operativamente existen cuatro grupos:

1. `runtime_contract`
   artefactos vivos del runtime
2. `accepted_project_operational_artifact`
   artefactos manual-especificos aceptados que sirven como soporte del proyecto actual
3. `historical_campaign_traceability`
   salidas de campanas historicas preservadas por trazabilidad
4. `debug_and_diagnostics`
   artefactos transitorios de auditoria y depuracion

Solo los artefactos de proyecto aceptado pueden usarse como input procesado autoritativo de un rebuild limpio. Los artefactos historicos y diagnosticos no deben definir el camino del runtime.

## Calidad semantica del runtime

El runtime operativo actual incorpora una barrera explicita entre T-Box y A-Box:

- `ontology_aligned.ttl` declara clases, propiedades y axiomas permitidos
- `abox_linked.ttl` materializa individuos y enlaces entre individuos
- los objetos de `rdf:type` no se mintean, no se canonicalizan y no se tratan como entidades A-Box
- GraphDB publica el resultado ya saneado, no corrige duplicados ni fusiona por labels

La validacion semantica bloquea:

- clases o propiedades no canonicas
- individuos usados como clases
- blank nodes de dominio
- IRIs `file:///`
- tipos redundantes explicitos
- sujetos sin tipo o sin trazabilidad

La deuda historica de `long_local_name` se mantiene como diagnostico de fase 1, no como hard failure.

## Enriquecimiento T-Box evidenciado

La T-Box puede enriquecerse solo con axiomas sobre vocabulario existente y con evidencia del runtime. El auditor:

- `src/6_extraction/tbox_enrichment_auditor.py`

produce:

- `data/processed/t_tbox_enrichment_evidence.json`

Tras C13, la T-Box incluye axiomas seguros como:

- `ex:Esquema rdfs:subClassOf ex:Figura`
- `ex:Maquina owl:disjointWith ex:Manual, ex:Directiva, ex:PiezaRecambio`
- `ex:Empresa owl:disjointWith ex:Directiva`

Despues de cualquier cambio en la T-Box se debe regenerar:

- `data/processed/schema_condensed.txt`

con:

```bash
python src/8_retrieval/schema_condenser.py
```

## Carriles del repositorio

### Carril operativo

Es el camino oficial de build, consulta, evaluacion y publicacion del runtime. Se apoya principalmente en:

- `src/1_ingestion/`
- `src/6_extraction/`
- `src/7_database/`
- `src/8_retrieval/`
- `run_runtime_clean_rebuild.py`
- `run_operational_pipeline.py`

### Carriles legacy o experimentales

Se conservan, pero no forman parte del runtime por defecto:

- `src/2_extraction/`
- `src/3_merging/`
- `src/5_alignment/`

## Tooling historico

Los siguientes scripts y areas se conservan por trazabilidad, pero estan fuera del camino operativo primario:

- `history/tooling/campaigns/run_t25_sequential_integration.py`
- `history/tooling/campaigns/run_t25_2_installation_recovery.py`
- `history/tooling/campaigns/run_t26_error_manual_onboarding.py`
- `history/tooling/diagnostics/check_mistral_api_usage.py`
- `history/tooling/runtime_clean_rebuild_plan.md`
- `misc/coding-team/repo-reusability-core-split/`

Se conservan shims de compatibilidad en la raiz para los wrappers historicos y la utilidad de diagnostico, pero su ubicacion canonica ya no es la raiz del repositorio.

Ninguno de ellos debe presentarse como entrypoint normal del runtime.

## Preparacion para split futuro

El siguiente split de repositorio no debe empezar desde cero. La referencia contractual actual para lo que pertenece al caso brochadora/CNC 8070 queda visible en:

- `projects/broaching-cnc-8070/project_scope_manifest.json`
- `data/processed/t27_project_specific_boundary_registry.json`

Mientras ese split no exista, las rutas vivas siguen donde estan hoy por compatibilidad operativa.

## Requisitos

- Python 3.10 o superior
- dependencias instaladas con `pip install -r requirements.txt`
- GraphDB disponible si se quiere publicar o consultar el mirror remoto
- `MISTRAL_API_KEY` para extraccion u operaciones que requieran LLM

El extractor soporta una cadena de fallback entre modelos Mistral para que un `429` en un modelo no detenga todo el proceso si el siguiente sigue disponible.

## Documentacion relacionada

- [docs/README.md](docs/README.md)
- [docs/operational_pipeline_runbook.md](docs/operational_pipeline_runbook.md)
- [docs/operational_artifact_contract.md](docs/operational_artifact_contract.md)
- [src/6_extraction/README.md](src/6_extraction/README.md)
- [src/7_database/README.md](src/7_database/README.md)
- [src/8_retrieval/README.md](src/8_retrieval/README.md)
