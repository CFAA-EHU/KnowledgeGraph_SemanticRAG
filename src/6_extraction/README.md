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

## Frontera A-Box/T-Box

La regla central del carril operativo es:

- la T-Box define clases, propiedades y axiomas permitidos
- el A-Box materializa individuos y relaciones entre individuos

El extractor y las etapas estructurales no deben crear clases nuevas, propiedades nuevas ni usar individuos como objeto de `rdf:type`.

El objeto de `rdf:type` es frontera dura. Por ejemplo:

```ttl
ex:SistemaCNC rdf:type ex:Sistema .
```

es valido si `ex:Sistema` existe como clase en `ontology_aligned.ttl`. En cambio, un tipo como `ex:Sistema_abc123` es invalido si representa un individuo A-Box.

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
- fallback entre modelos Mistral cuando un modelo queda limitado por cuota o rate limit
- saneamiento RDF antes de validar y escribir TTL
- endurecimiento del prompt para evitar que el modelo cree clases, propiedades o IRIs desde frases largas

Reglas relevantes del prompt y del post-proceso:

- `rdf:type` solo puede apuntar a clases declaradas en la T-Box
- no se construyen IRIs a partir de `textoExtracto`
- cada entidad debe tener una surface breve, preferentemente `rdfs:label` o `identificador`
- `textoExtracto` es evidencia, no identidad
- los local names nuevos creados por saneado se limitan a 80 caracteres

### 3. `abox_merger.py`

Fusiona todos los TTL por chunk ya validados en un unico snapshot bruto:

- entrada: `*_abox.ttl`
- salida: `data/processed/abox_merged.ttl`

Este merge es estructural. No decide equivalencias semanticas ni resuelve entidades duplicadas.

Antes de fusionar cada chunk, el merger ejecuta saneado y validacion semantica. Un chunk con hard failures no entra en `abox_merged.ttl` y queda trazado en:

- `data/processed/abox_merger_rejected_chunks.json`

El saneado final del grafo fusionado es parcial y no minta IRIs nuevas. Solo aplica defensas idempotentes como:

- downgrade de literales `xsd:hexBinary` invalidos
- eliminacion de supertypes redundantes
- limpieza o acotacion de `textoExtracto`
- eliminacion de tipos `Tabla` incidentales en entradas que realmente son funciones, parametros, modos o comandos

El reporte de colisiones:

- `data/processed/abox_merged_uri_collision_report.json`

puede existir aunque el merge sea valido. El criterio operativo es que no exista o que tenga `blocker_count = 0`.

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

La canonicalizacion reescribe sujetos y objetos de relaciones ordinarias, pero no reescribe objetos de `rdf:type`. Esta proteccion evita convertir clases T-Box en individuos canonicos.

La compatibilidad de tipos es conservadora:

- tipos iguales son compatibles
- subtipo/supertipo declarados con `rdfs:subClassOf` son compatibles
- pares declarados con `owl:disjointWith` no se fusionan
- pares manualmente conflictivos siguen actuando como fallback
- tipos distintos sin jerarquia no se fusionan solo por similitud textual

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
- surface enrichment solo con `rdfs:label` y propiedades de datos declaradas en la T-Box
- no se anaden surfaces con object properties ni `rdf:type`
- no se anaden valores de surface largos

El reporte incluye validacion semantica del snapshot enriquecido.

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

Antes de anadir un enlace, el link completer valida que:

- source y target sean individuos tipados
- source y target no sean clases T-Box
- el predicado sea una `owl:ObjectProperty`
- el enlace no sea un self-loop

Si `abox_linked.ttl` contiene hard failures semanticos, la etapa falla y no debe publicarse.

### 7. `abox_graph_sanitizer.py`

Saneador RDF comun, idempotente y reutilizado por extractor, merger, canonicalizer, enricher y link completer.

Corrige o controla:

- blank nodes de dominio como sujeto u objeto
- IRIs `file:///`
- objetos de `rdf:type` protegidos frente a minting/remapping
- supertypes redundantes
- local names nuevos demasiado largos
- uso indebido de `textoExtracto` como identidad
- sujetos con surface/enlaces pero sin tipo inferible de forma segura
- sujetos tipados sin trazabilidad textual minima

El saneador mantiene el registro persistente:

- `data/processed/abox_minted_entity_registry.json`

Ese registro evita que ejecuciones parciales generen IRIs distintas para el mismo patron superficial.

### 8. `abox_semantic_validator.py`

Validador semantico de snapshots A-Box.

Hard failures:

- clase no canonica en `rdf:type`
- propiedad no canonica
- sujeto de dominio sin tipo
- sujeto tipado sin trazabilidad
- blank node de dominio
- IRI `file:///`
- tipo redundante explicito
- individuo usado como clase

Diagnosticos no bloqueantes en fase actual:

- `weak_linkage`
- `long_local_name`
- `no_useful_links`

### 9. `tbox_enrichment_auditor.py`

Audita el uso real de `abox_linked.ttl` frente a `ontology_aligned.ttl` para justificar enriquecimientos de T-Box.

Produce:

- `data/processed/t_tbox_enrichment_evidence.json`

Este modulo no crea clases ni propiedades nuevas. Solo genera evidencia para axiomas sobre vocabulario ya existente.

### 10. `src/8_retrieval/multilingual_lexicon_builder.py`

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

Tambien genera `data/processed/abox_semantic_audit.json` cuando se ejecuta como auditoria de snapshot.

### `canonical_resolution_policy.py`

Define las reglas de consolidacion canonica:

- agrupacion de candidatos
- criterios de seleccion del nodo canonico
- casos donde no se debe consolidar
- compatibilidad por `rdfs:subClassOf`
- bloqueo por `owl:disjointWith`

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
- `abox_semantic_audit.json`
- `abox_merger_rejected_chunks.json`
- `abox_minted_entity_registry.json`
- `t_tbox_enrichment_evidence.json`

## Estado operativo actual

El runtime publicado tras la estabilizacion A-Box/T-Box cumple:

- `blank nodes` de dominio: 0
- IRIs `file:///`: 0
- `non_canonical_class`: 0
- `individual_used_as_class`: 0
- `missing_type`: 0
- `missing_traceability`: 0
- `redundant_type_assertion`: 0
- `abox_merged_uri_collision_report.blocker_count`: 0

`long_local_name` permanece como diagnostico de deuda historica, no como hard failure de fase 1.

## Que hace y que no hace este directorio

### Si hace

- extraccion A-Box operativa por chunk
- validacion TTL
- validacion semantica por snapshot
- saneado RDF idempotente
- merge estructural
- consolidacion canonica
- enrichment residual
- link completion residual controlado
- auditoria evidenciada para enriquecimiento T-Box

### No hace

- construccion o reduccion experimental de T-Box
- clustering semantico libre de instancias fuera de politica
- planificacion SPARQL
- sintesis de respuestas
- publicacion en GraphDB
- migraciones en caliente sobre GraphDB existente

Esas responsabilidades viven en otros directorios.

## Ejecucion habitual

La forma normal de ejecutar este carril es a traves del runner operativo:

```bash
python run_operational_pipeline.py --mode resume-compatible
```

Para trabajar con un manual concreto se puede generar un carril parametrizado con `--source-chunks` y `--manual-id`, manteniendo el mismo pipeline estructural.

Validaciones recomendadas:

```bash
python -m unittest
python src/6_extraction/abox_semantic_validator.py --abox-path data/processed/abox_linked.ttl
python src/6_extraction/tbox_enrichment_auditor.py
```
