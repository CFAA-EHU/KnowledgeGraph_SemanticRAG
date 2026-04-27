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

La publicacion recrea el repositorio operativo antes de importar los TTL. Esto es intencional: el runtime se corrige por regeneracion completa y reimportacion, no por migraciones en caliente sobre el grafo existente.

Antes de publicar debe existir una auditoria A-Box aceptable:

- `data/processed/abox_semantic_audit.json`

El A-Box final no debe contener hard failures como blank nodes de dominio, IRIs `file:///`, clases no canonicas, individuos usados como clases, sujetos sin tipo o sujetos sin trazabilidad.

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

El healthcheck esperado tras la publicacion operativa es:

- `status = repository_ready`
- `repository_has_data = true`
- `errors = []`

El triple count puede cambiar cuando se regeneran snapshots o se enriquece la T-Box. El ultimo runtime saneado y publicado tras C13 contiene `91270` triples en GraphDB.

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

## Relacion con la T-Box enriquecida

GraphDB publica la T-Box operativa junto con el A-Box final. La T-Box puede incluir axiomas de soporte para validacion y canonicalizacion, por ejemplo:

- `rdfs:subClassOf`
- `owl:disjointWith`
- dominios y rangos declarados

Estos axiomas no se deben usar para ocultar duplicados de identidad que el pipeline pueda resolver antes de publicacion. La regla preferida sigue siendo materializar una unica URI canonica en `abox_linked.ttl` y publicar ese grafo ya saneado.
