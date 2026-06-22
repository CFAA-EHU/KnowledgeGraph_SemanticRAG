# src/7_database

Local RDF backend and GraphDB mirror for the operational A-Box graph.

## Files

### publish_to_graphdb.py

Deletes the existing GraphDB repository, recreates it, and uploads the T-Box and operational A-Box. Target repository: `semanticrag_operational_mirror` at `http://localhost:7200`.

```bash
python src/7_database/publish_to_graphdb.py
```

### graphdb_healthcheck.py

Verifies GraphDB availability, confirms the repository exists and contains the expected triple count.

```bash
python src/7_database/graphdb_healthcheck.py
```

### graph_store.py

Provides programmatic access to the operational graph via SPARQL. Supports both `rdflib` (local) and GraphDB (remote) backends. Used internally by `query_workbench.py` and the evaluation pipeline.

### embedded_store.py

Direct SPARQL interface to the local RDFLib graph without planner or synthesis. Used for low-level inspection.

### graphdb_client.py

HTTP client wrapper for GraphDB SPARQL endpoints. Handles authentication, retry logic, and response parsing.

## Backend selection

`rdflib` is the reference backend and the safe fallback. GraphDB mirrors the same graph and is used when the remote endpoint is available.

`query_workbench.py` selects the backend via `--backend rdflib` or `--backend graphdb`.
