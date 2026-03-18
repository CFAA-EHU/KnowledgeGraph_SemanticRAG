
# src/2_extraction — Carril experimental de T-Box

Este directorio contiene el flujo experimental de construcción dinámica de T-Box a partir del manual.

## Estado actual
Este carril se conserva por motivos de investigación, comparación y prototipado, pero **ya no define el flujo operativo principal** del proyecto.

El runtime actual no depende de estos artefactos para:
- construir la A-Box operativa
- cargar el store
- ejecutar retrieval
- evaluar el sistema

## Scripts principales

### `prompt_assembler.py`
Construye prompts de extracción de T-Box a partir de:
- `data/raw/density_report.json`
- `cache/terms_cache.json`

Genera:
- `data/processed/tbox_prompts.json`

### `llm_extractor.py`
Ejecuta la extracción experimental de T-Box sobre los prompts ensamblados.

## Artefactos experimentales asociados
- `data/processed/tbox_prompts.json`
- `data/processed/graphs/*.ttl`
- `data/processed/ontology_merged.ttl`

## Relación con el carril operativo
El carril operativo **no puede** usar `tbox_prompts.json` como input de A-Box.

La separación entre carriles está documentada en:
- `artifact_contracts.py`
- `docs/operational_artifact_contract.md`

## Cuándo usar este directorio
Úsalo solo si quieres:
- investigar generación dinámica de ontología
- comparar T-Box experimental vs T-Box canónica
- prototipar nuevos prompts de T-Box

No lo uses para build operativo.