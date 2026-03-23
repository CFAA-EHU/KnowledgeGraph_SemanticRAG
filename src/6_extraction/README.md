# src/6_extraction - Extraccion A-Box operativa

Este directorio implementa el carril operativo de construccion de A-Box.

## Objetivo
Transformar chunks del manual en instancias RDF validas, semanticamente aceptables, consolidadas sobre entidades canonicas, enriquecidas con linking/value surfaces genericos y rematadas con link completion residual antes del runtime.

## Flujo operativo

### 1. `abox_input_builder.py`
Genera `data/processed/abox_input.json` a partir del material operativo limpio.

### 2. `abox_extractor.py`
Lee `abox_input.json` y `ontology_aligned.ttl`, genera `data/processed/abox_graphs/*_abox.ttl` y mantiene `abox_generation_manifest.json` con validacion TTL y validacion semantica ligera.

### 3. `abox_merger.py`
Fusiona `data/processed/abox_graphs/*_abox.ttl` y genera `data/processed/abox_merged.ttl`.

### 4. `canonical_resolution_policy.py`
Define la politica generica de consolidacion:
- agrupacion de candidatos por tipo, identificador y superficie
- seleccion de nodo canonico
- criterios de no consolidacion
- trazabilidad de reglas aplicadas

### 5. `abox_canonicalizer.py`
Carga `abox_merged.ttl`, reescribe enlaces y genera:
- `data/processed/abox_canonical.ttl`
- `data/processed/canonical_entity_map.json`
- `data/processed/canonicalization_report.json`
- `data/processed/canonicalization_resolution_candidates.json`

### 6. `enrichment_policy.py`
Define la politica generica de enrichment residual:
- linking enrichment solo cuando la correspondencia estructural es fuerte
- surface enrichment solo con `label`, `identificador`, `textoExtracto` y `valor`
- reglas de no enrichment para casos ambiguos o especulativos

### 7. `abox_graph_enricher.py`
Carga `abox_canonical.ttl`, anade enlaces y surfaces utiles, y genera:
- `data/processed/abox_enriched.ttl`
- `data/processed/enrichment_report.json`
- `data/processed/enrichment_link_map.json`
- `data/processed/enrichment_surface_map.json`
- `data/processed/enrichment_resolution_candidates.json`

### 8. `link_completion_policy.py`
Define la politica de link completion residual:
- solo familias observadas realmente en T18
- targets unicos y tipado compatible
- derivacion desde texto solo con evidencia alta e inequivoca
- rechazo explicito para familias bloqueadas o ambiguas

Whitelist inicial de T19:
- activas: `declaration_signatory_link`, `lockout_warning_link`, `panel_control_set_link`, `machine_operating_modes_link`, `manual_greasing_task_link`
- bloqueadas: `emergency_button_usage_condition`, `operator_ppe_requirement`

### 9. `abox_link_completer.py`
Carga `abox_enriched.ttl`, materializa solo los enlaces residuales aprobados por whitelist y genera:
- `data/processed/abox_linked.ttl`
- `data/processed/link_completion_candidates.json`
- `data/processed/link_completion_map.json`
- `data/processed/link_completion_report.json`

## Contrato operativo actual
- `abox_merged.ttl`: artefacto bruto intermedio
- `abox_canonical.ttl`: artefacto canonico intermedio
- `abox_enriched.ttl`: artefacto enriquecido intermedio
- `abox_linked.ttl`: artefacto operativo final consumido por runtime
- la trazabilidad de consolidacion, enrichment y link completion vive en JSON, no en duplicados vivos dentro del grafo operativo

## Ejecucion
Normalmente este directorio se ejecuta via:

```bash
python run_operational_pipeline.py --mode resume-compatible
```
