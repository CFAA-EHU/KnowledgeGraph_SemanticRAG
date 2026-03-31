# src/6_extraction - Carril operativo de construccion de A-Box

Este directorio implementa el pipeline que transforma chunks de manuales en un unico grafo A-Box operativo para consulta, evaluacion y publicacion en GraphDB.

## Objetivo

Convertir texto tecnico chunkificado en instancias RDF:

- sintacticamente validas
- semanticamente compatibles con la T-Box operativa
- consolidadas sobre entidades canonicas
- enriquecidas con surfaces y enlaces de alta confianza
- rematadas con un link completion residual controlado

El resultado final de este carril es `data/processed/abox_linked.ttl`.

## Rol dentro del runtime

Este directorio forma el carril estructural principal del runtime actual.

El flujo operativo consume:

- `data/processed/ontology_aligned.ttl`
- un payload de entrada A-Box derivado de un `density_report`

Y produce:

- `data/processed/abox_merged.ttl`
- `data/processed/abox_canonical.ttl`
- `data/processed/abox_enriched.ttl`
- `data/processed/abox_linked.ttl`

El runtime de consulta consume `ontology_aligned.ttl` mas `abox_linked.ttl`.

## Flujo del pipeline

### 1. `abox_input_builder.py`

Construye el payload de entrada para la extraccion A-Box a partir de un `density_report`.

Cada entrada contiene, entre otros campos:

- `chunk_id`
- `manual_id`
- `texto_fuente`
- `paginas`
- `seccion`
- `titulo`
- `density_level`
- `terms_found`
- `source_language`
- `language_confidence`
- `source_path`
- `chunk_hash`

Punto importante:

- `data/processed/abox_input.json` no es un inventario acumulativo de todos los manuales integrados.
- Es el snapshot de entrada generado a partir de un unico `density_report` de trabajo.
- Cuando se hace onboarding de un manual concreto, es normal generar archivos separados como `quick_ref_abox_input.json`, `installation_manual_abox_input.json` o `man_8070_err_abox_input.json`.

### 2. `abox_extractor.py`

Lee el A-Box input, carga la T-Box operativa y llama al modelo para generar TTL por chunk.

Responsabilidades principales:

- construir el prompt de extraccion A-Box
- normalizar el TTL devuelto por el modelo
- validar sintaxis Turtle
- validar compatibilidad semantica basica con el vocabulario permitido
- persistir un TTL por chunk
- mantener un manifest de reanudacion
- guardar artefactos de debug por chunk fallido
- aplicar perfiles de retry y backoff

Este script tambien protege el runtime frente a salidas defectuosas del modelo:

- reintentos controlados
- clasificacion de errores retryable y non-retryable
- reanudacion por chunk
- saneamiento de ciertos literales problematicos antes de escribir TTL

### 3. `abox_merger.py`

Fusiona todos los TTL por chunk ya validados en un unico snapshot bruto:

- entrada: `*_abox.ttl`
- salida: `data/processed/abox_merged.ttl`

Este merge es estructural. No decide equivalencias semanticas ni resuelve entidades duplicadas.

### 4. `abox_canonicalizer.py`

Consolida entidades equivalentes o redundantes sobre nodos canonicos.

Trabaja sobre:

- `data/processed/abox_merged.ttl`

Produce:

- `data/processed/abox_canonical.ttl`
- `data/processed/canonical_entity_map.json`
- `data/processed/canonicalization_report.json`
- `data/processed/canonicalization_resolution_candidates.json`

Su objetivo es reducir duplicados operativos sin abrir una alineacion libre basada solo en similitud textual.

### 5. `abox_graph_enricher.py`

Anade enriquecimiento residual de alta confianza sobre el grafo canonizado.

Trabaja sobre:

- `data/processed/abox_canonical.ttl`

Produce:

- `data/processed/abox_enriched.ttl`
- `data/processed/enrichment_report.json`
- `data/processed/enrichment_link_map.json`
- `data/processed/enrichment_surface_map.json`
- `data/processed/enrichment_resolution_candidates.json`

El enrichment esta restringido para no introducir ruido semantico:

- linking enrichment solo con evidencia estructural fuerte
- surface enrichment solo con `label`, `identificador`, `textoExtracto` y `valor`

### 6. `abox_link_completer.py`

Materializa un conjunto muy limitado de enlaces residuales permitidos por politica.

Trabaja sobre:

- `data/processed/abox_enriched.ttl`

Produce:

- `data/processed/abox_linked.ttl`
- `data/processed/link_completion_candidates.json`
- `data/processed/link_completion_map.json`
- `data/processed/link_completion_report.json`

Este es el ultimo paso estructural del pipeline. `abox_linked.ttl` es el artefacto final que usa el runtime.

### 7. `src/8_retrieval/multilingual_lexicon_builder.py`

Aunque vive fuera de este directorio, se ejecuta inmediatamente despues del build estructural.

Produce:

- `data/processed/multilingual_lexicon.json`

Ese artefacto lexicaliza el grafo unico en varios idiomas para planner y sintesis, sin duplicar URIs ni traducir `textoExtracto` dentro del RDF.

## Modulos auxiliares y de politica

### `abox_resume_policy.py`

Gestiona el manifest del extractor y decide si un chunk:

- se reutiliza
- se regenera
- se marca como `missing`, `stale` o `error`

Es el modulo que permite reanudacion fina sin reprocesar todo.

### `abox_ttl_validator.py`

Valida la sintaxis Turtle de texto generado o de archivos ya escritos.

### `abox_semantic_validator.py`

Comprueba que el TTL use clases y propiedades compatibles con la T-Box operativa.

### `canonical_resolution_policy.py`

Define las reglas de consolidacion canonica:

- agrupacion de candidatos
- criterios de seleccion del nodo canonico
- casos donde no se debe consolidar

### `enrichment_policy.py`

Define las reglas del enrichment residual:

- cuando se puede anadir linking
- que surfaces pueden anadirse
- que casos deben rechazarse por ambiguedad

### `link_completion_policy.py`

Define la whitelist del link completion residual:

- familias activas
- restricciones de tipado
- requisitos de evidencia
- familias bloqueadas

## Artefactos principales

### Input

- `data/raw/*.txt`
- `data/raw/density_report.json` o un `density_report` equivalente por manual
- `data/processed/ontology_aligned.ttl`

### Intermedios

- `data/processed/abox_input.json`
- `data/processed/abox_merged.ttl`
- `data/processed/abox_canonical.ttl`
- `data/processed/abox_enriched.ttl`

### Finales

- `data/processed/abox_linked.ttl`
- `data/processed/multilingual_lexicon.json`

### Trazabilidad

- manifest de generacion A-Box
- reportes de canonicalizacion
- mapas de enrichment
- reportes y mapas de link completion
- artefactos de debug por chunk cuando falla la extraccion

## Que hace y que no hace este directorio

### Si hace

- extraccion A-Box operativa por chunk
- validacion TTL
- validacion semantica ligera
- merge estructural
- consolidacion canonica
- enrichment residual
- link completion residual controlado

### No hace

- construccion o reduccion experimental de T-Box
- clustering semantico libre de instancias fuera de politica
- planificacion SPARQL
- sintesis de respuestas
- publicacion en GraphDB

Esas responsabilidades viven en otros directorios.

## Ejecucion habitual

La forma normal de ejecutar este carril es a traves del runner operativo:

```bash
python run_operational_pipeline.py --mode resume-compatible
```

Para trabajar con un manual concreto se puede generar un carril parametrizado con `--source-chunks` y `--manual-id`, manteniendo el mismo pipeline estructural.
