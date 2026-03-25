# src/7_database - Stores RDF, GraphDB espejo y ejecucion SPARQL

Este directorio contiene el runtime minimo de carga y consulta del knowledge graph operativo, ahora con dos backends:
- `rdflib` en memoria como backend de referencia
- `GraphDB` remoto como backend espejo opcional

## Componentes principales

### `embedded_store.py`
Herramienta manual de SPARQL con selector:
- `--backend rdflib`
- `--backend graphdb`

Mantiene `rdflib` como modo por defecto seguro.
Uso recomendado:
- inspeccion SPARQL directa
- pruebas manuales sin planner ni sintesis

Patron de uso deprecado:
- no usarlo como sustituto de `query_workbench.py` para preguntas en lenguaje natural

### `graphdb_client.py`
Cliente minimo reutilizable para GraphDB. Expone:
- healthcheck
- comprobacion y creacion de repositorio
- subida de Turtle
- ejecucion `SELECT`
- ejecucion `ASK`

### `graph_store.py`
Capa minima comun de acceso al grafo con dos implementaciones:
- `RDFLibGraphStore`
- `GraphDBGraphStore`

Tambien puede generar la verificacion basica de equivalencia RDFLib vs GraphDB.
No contiene logica de planner ni de sintesis.

### `publish_to_graphdb.py`
Publica los artefactos operativos ya existentes en GraphDB:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_linked.ttl`

Genera:
- `data/processed/graphdb_publication_report.json`

### `graphdb_healthcheck.py`
Comprueba:
- disponibilidad del servidor
- existencia del repositorio
- respuesta del endpoint SPARQL
- si el repositorio esta vacio o listo

## Objetivo
Servir como backend simple para:
- validacion manual de consultas SPARQL
- retrieval automatico
- evaluacion
- smoke tests del runtime
- publicacion del grafo operativo en GraphDB como espejo
- exploracion visual y consulta remota del grafo cuando GraphDB este disponible

## Publicacion y pruebas minimas

Publicar el grafo operativo:

```bash
python src/7_database/publish_to_graphdb.py
```

Comprobar el backend espejo:

```bash
python src/7_database/graphdb_healthcheck.py
```

Comparar equivalencia basica:

```bash
python src/7_database/graph_store.py
```

Probar SPARQL manual en GraphDB:

```bash
python src/7_database/embedded_store.py --backend graphdb
```

Probar una pregunta manual con planner y trazas:

```bash
python query_workbench.py "¿Qué directiva cumple la máquina?" --backend graphdb
```

## Garantia de contrato
Los stores consumen solo artefactos del carril operativo final:
- `ontology_aligned.ttl`
- `abox_linked.ttl`

`abox_merged.ttl` queda reservado como snapshot bruto, `abox_canonical.ttl` como snapshot intermedio de consolidacion y `abox_enriched.ttl` como snapshot previo al link completion residual. Ninguno de ellos debe tratarse como runtime final.

GraphDB entra como backend espejo del runtime actual. No sustituye todavia a `rdflib` como backend de referencia ni como backend por defecto del planner y la evaluacion.
