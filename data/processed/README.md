# data/processed - Artefactos operativos, historicos y diagnosticos

Este directorio contiene los artefactos generados por el pipeline. No debe tratarse como un espacio plano donde todos los JSON o TTL tienen el mismo rol.

## Contrato vivo del runtime

Artefactos principales consumidos por consulta, evaluacion y publicacion:

- `ontology_aligned.ttl`
- `abox_linked.ttl`
- `multilingual_lexicon.json`
- `schema_condensed.txt`

Snapshots estructurales del build:

- `abox_merged.ttl`
- `abox_canonical.ttl`
- `abox_enriched.ttl`

Reportes y mapas contractuales:

- `abox_semantic_audit.json`
- `abox_minted_entity_registry.json`
- `abox_merger_rejected_chunks.json`
- `canonical_entity_map.json`
- `canonicalization_report.json`
- `canonicalization_resolution_candidates.json`
- `enrichment_report.json`
- `enrichment_link_map.json`
- `enrichment_surface_map.json`
- `link_completion_report.json`
- `link_completion_map.json`
- `link_completion_candidates.json`
- `graphdb_publication_report.json`
- `t_tbox_enrichment_evidence.json`

## Artefactos manual-especificos aceptados

Los prefijos `a218_*`, `quick_ref_*`, `installation_manual_*`, `8070_installation_*` y `man_8070_err_*` pertenecen al proyecto de referencia brochadora/CNC 8070. Son utiles para trazabilidad y rebuild, pero no sustituyen al contrato final `abox_linked.ttl`.

## Historico y diagnostico

Los artefactos `t21_*`, `t22_*`, `t23_*`, `t24_*`, `t25_*`, `t26_*`, `t27_*`, `*_debug_report.json` y reportes de recovery/campaign son trazabilidad historica o diagnostica. No deben usarse como fuente contractual de un rebuild limpio.

## Criterios actuales de sanidad RDF

El snapshot operativo final debe cumplir:

- 0 blank nodes de dominio como sujeto u objeto
- 0 IRIs `file:///`
- 0 clases no canonicas en `rdf:type`
- 0 individuos usados como clases
- 0 sujetos de dominio sin tipo
- 0 sujetos tipados sin trazabilidad
- 0 tipos redundantes explicitos
- `abox_merged_uri_collision_report.json` ausente o con `blocker_count = 0`

`long_local_name` y `weak_linkage` son diagnosticos de fase actual.

## GraphDB

`graphdb_publication_report.json` documenta la ultima publicacion del mirror GraphDB. La estrategia operativa es reimportacion completa: no se hacen migraciones en caliente sobre el grafo publicado.
