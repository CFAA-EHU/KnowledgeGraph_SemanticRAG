# docs

Indice de la documentacion contractual y operativa del repositorio.

## Empieza por aqui

- [README.md](..\README.md)
  Vista general del framework, frontera entre core reusable y contenido project-specific, entrypoints oficiales y contrato vivo del runtime.

- [operational_pipeline_runbook.md](operational_pipeline_runbook.md)
  Camino operativo estable para rebuild, onboarding puntual, evaluacion, consulta y GraphDB.

- [operational_artifact_contract.md](operational_artifact_contract.md)
  Contrato de artefactos del carril operativo.

## Documentacion modular

- [src/6_extraction/README.md](..\src\6_extraction\README.md)
  Construccion operativa del A-Box y significado de cada snapshot estructural.

- [src/7_database/README.md](..\src\7_database\README.md)
  Backend RDF local, mirror GraphDB y utilidades de publicacion y healthcheck.

- [src/8_retrieval/README.md](..\src\8_retrieval\README.md)
  Planner, retrieval, sintesis, evaluacion y workbench de consulta.

## Contrato documental actual

La documentacion del repositorio debe comunicar siempre estas reglas:

- el repositorio es un framework reusable con un proyecto de referencia retenido dentro del mismo repo
- `run_runtime_clean_rebuild.py` es el unico rebuild primario documentado
- `run_operational_pipeline.py` es un entrypoint estable de soporte para build tactico y onboarding de un manual
- `src/2_extraction/`, `src/3_merging/` y `src/5_alignment/` son carriles legacy o experimentales, no pasos del runtime por defecto
- los scripts `run_t25*`, `run_t26*` y utilidades de recovery o smoke test quedan desclasificados del camino operativo primario
- `data/processed` contiene artefactos con semantica distinta: runtime vivo, proyecto aceptado, historia de campanas y diagnostico

## Fuera del camino operativo primario

Estas piezas pueden seguir siendo utiles para trazabilidad, investigacion o contexto, pero no deben presentarse como contrato normal del runtime:

- `run_t25_sequential_integration.py`
- `run_t25_2_installation_recovery.py`
- `run_t26_error_manual_onboarding.py`
- `check_mistral_api_usage.py`
- `docs/runtime_clean_rebuild_plan.md`
- `misc/coding-team/repo-reusability-core-split/`
