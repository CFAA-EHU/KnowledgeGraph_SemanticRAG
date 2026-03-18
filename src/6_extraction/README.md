# src/6_extraction — Extracción A-Box operativa

Este directorio implementa el carril operativo de construcción de A-Box.

## Objetivo
Transformar chunks del manual en instancias RDF válidas y semánticamente aceptables contra la T-Box canónica.

## Flujo operativo

### 1. `abox_input_builder.py`
Deriva el payload operativo desde `data/raw/density_report.json` y genera:

- `data/processed/abox_input.json`

Cada entrada contiene, como mínimo:
- `chunk_id`
- `texto_fuente`
- `paginas`
- `seccion`
- `titulo`
- `density_level`

Y además trazabilidad útil como:
- `terms_found`
- `source_path`
- `chunk_hash`

### 2. `abox_extractor.py`
Lee:
- `data/processed/abox_input.json`
- `data/processed/ontology_aligned.ttl`

Genera:
- `data/processed/abox_graphs/*_abox.ttl`
- `data/processed/abox_generation_manifest.json`
- artefactos de debug puntuales en `data/processed/abox_debug/`

Características actuales:
- reanudación compatible (`resume-compatible`, `force-stale`, `force-all`)
- validación TTL antes de marcar `ok`
- validación semántica ligera contra la T-Box canónica
- persistencia de `semantic_report`
- clasificación de `error_cause`
- guardrails semánticas activas
- material de diagnóstico para chunks fallidos

### 3. `abox_resume_policy.py`
Gestiona:
- firma de compatibilidad
- decisión de reutilización
- estados por chunk
- persistencia del manifiesto

### 4. `abox_ttl_validator.py`
Valida sintaxis Turtle antes de aceptar un chunk como válido.

### 5. `abox_semantic_validator.py`
Verifica conformidad semántica ligera:
- clases canónicas
- propiedades canónicas
- sujetos tipados
- checks estructurales mínimos

### 6. `abox_merger.py`
Fusiona:
- `data/processed/abox_graphs/*_abox.ttl`

y genera:
- `data/processed/abox_merged.ttl`

## Artefactos operativos clave
- `data/processed/abox_input.json`
- `data/processed/abox_generation_manifest.json`
- `data/processed/abox_semantic_audit.json`
- `data/processed/abox_merged.ttl`

## Criterio de aceptación actual
La A-Box no se acepta solo por parsear como Turtle.  
Debe además ser compatible con:
- la T-Box canónica
- las guardrails semánticas vigentes
- el criterio de `acceptable_for_phase`

## Ejecución
Normalmente este directorio se ejecuta vía:

```bash
python run_operational_pipeline.py --mode resume-compatible