# src/5_alignment - Alineamiento experimental de A-Box

Este directorio contiene utilidades experimentales de alineamiento semantico de instancias A-Box.

## Estado actual

- `semantic_reduction.py` no forma parte del runtime operativo actual.
- Se conserva solo para pruebas de deduplicacion y consolidacion fuera del carril oficial.

## Inputs y outputs

Lee:
- `data/processed/abox_linked.ttl`

Genera:
- `data/processed/abox_aligned.ttl`

## Importante

- El runtime operativo consume `ontology_aligned.ttl` y `abox_linked.ttl`.
- `abox_aligned.ttl` es un artefacto experimental y no se usa en consulta, evaluacion ni GraphDB por defecto.
