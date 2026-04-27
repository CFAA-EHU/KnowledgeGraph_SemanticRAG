# tests - Validacion automatica del runtime operativo

Este directorio contiene tests unitarios y de integracion ligera para las capas criticas del pipeline.

## Cobertura principal

- `test_abox_graph_sanitizer.py`
  valida saneado RDF idempotente, minting de IRIs, proteccion de objetos `rdf:type`, limpieza de `file:///`, tipos redundantes, `textoExtracto`, registro persistente y reparaciones minimas de tipo/trazabilidad.

- `test_abox_semantic_validator.py`
  valida deteccion de hard failures como individuos usados como clases y diagnosticos como `long_local_name`.

- `test_abox_merger_chunk_sanitization.py`
  valida que el merger rechace chunks con hard failures y que el saneado final del grafo fusionado no mintee IRIs nuevas.

- `test_abox_canonicalizer.py`
  valida que canonicalizer no reescriba objetos de `rdf:type` ni genere enlaces suplementarios sobre triples de tipado.

- `test_abox_enrichment_guards.py`
  valida guards de enrichment y link completion: predicados permitidos, valores largos, endpoints tipados, clases T-Box y self-loops.

- `test_canonical_resolution_policy.py`
  valida compatibilidad conservadora por tipos, jerarquias `rdfs:subClassOf` y bloqueos `owl:disjointWith`.

- `test_tbox_enrichment_auditor.py`
  valida generacion de evidencia para C13 sin crear clases ni propiedades nuevas.

- `test_text_to_sparql_seed_resolution.py`
  cubre resolucion de semillas del planner.

## Ejecucion

```bash
python -m unittest
```

La suite no reemplaza los gates operativos con golden sets. Antes de publicar un runtime tambien deben ejecutarse las auditorias y QA contractuales descritas en los README de `src/6_extraction`, `src/8_retrieval` y `src/7_database`.
