# src/6_extraction - Extraccion A-Box operativa

Este directorio implementa el carril operativo de construccion de A-Box.

## Objetivo
Transformar chunks del manual en instancias RDF validas, semanticamente aceptables, consolidadas sobre entidades canonicas, enriquecidas con linking/value surfaces genericos y rematadas con link completion residual antes del runtime.

Tras T20, este carril sigue produciendo un solo grafo operativo. El soporte bilingue no duplica entidades: preserva `source_language` en el onboarding y deja la lexicalizacion ES/EN reutilizable fuera del RDF, en `data/processed/multilingual_lexicon.json`.

## Flujo operativo

### 1. `abox_input_builder.py`
Genera `data/processed/abox_input.json` a partir del material operativo limpio.

Ahora arrastra tambien:
- `source_language`
- `language_confidence`
- `source_path`

Para onboarding piloto real tambien admite rutas parametrizadas, por ejemplo:
- `quick_ref_abox_input.json`

### 2. `abox_extractor.py`
Lee `abox_input.json` y `ontology_aligned.ttl`, genera `data/processed/abox_graphs/*_abox.ttl` y mantiene `abox_generation_manifest.json` con validacion TTL y validacion semantica ligera.

Regla bilingue de T20:
- `textoExtracto` y citas textuales deben conservar el idioma original del chunk
- las surfaces bilingues consultables no se generan aqui, sino despues en el lexicon multilingue

T21 reutiliza exactamente este mismo carril para `chunks_8070_quick_ref.txt`; no existe un extractor paralelo para manuales en ingles.

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

### 10. `src/8_retrieval/multilingual_lexicon_builder.py`
Se ejecuta despues del build estructural y produce:
- `data/processed/multilingual_lexicon.json`

Ese artefacto lexicaliza el grafo unico en ES/EN para planner y sintesis, sin duplicar URIs ni traducir `textoExtracto`.

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

Pilot lane reproducible:

```bash
python run_operational_pipeline.py --source-chunks data/raw/chunks_8070_quick_ref.txt --manual-id 8070_quick_ref --mode resume-compatible
```
