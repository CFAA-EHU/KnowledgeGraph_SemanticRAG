# src/7_database - Store RDF embebido y ejecucion SPARQL

Este directorio contiene el runtime minimo de carga y consulta del knowledge graph operativo.

## Script principal

### `embedded_store.py`
Carga en memoria:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_linked.ttl`

Y expone ejecucion SPARQL sobre el grafo combinado.

## Objetivo
Servir como backend simple para:
- validacion manual de consultas SPARQL
- retrieval automatico
- evaluacion
- smoke tests del runtime

## Garantia de contrato
El store consume solo artefactos del carril operativo final:
- `ontology_aligned.ttl`
- `abox_linked.ttl`

`abox_merged.ttl` queda reservado como snapshot bruto, `abox_canonical.ttl` como snapshot intermedio de consolidacion y `abox_enriched.ttl` como snapshot previo al link completion residual. Ninguno de ellos debe tratarse como runtime final.
