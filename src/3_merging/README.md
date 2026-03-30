# src/3_merging - Merge experimental de T-Box

Este directorio queda reservado al merge de TTLs del carril experimental T-Box.

## Estado actual

- `graph_merger.py` no forma parte del runtime operativo.
- Su unica responsabilidad es fusionar `data/processed/graphs/*.ttl` en `data/processed/ontology_merged.ttl`.
- Ese artefacto es exploratorio y no debe confundirse con `ontology_aligned.ttl`, que sigue siendo la T-Box operativa.

## Uso

Solo tiene sentido despues de ejecutar el carril experimental de `src/2_extraction/`.
