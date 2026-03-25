# docs

Indice de documentacion operativa, contractual y transversal del proyecto.

## Empieza por aqui

- [README.md](..\README.md)
  Vista general del repositorio, entrypoints oficiales y estado operativo actual.

- [operational_pipeline_runbook.md](operational_pipeline_runbook.md)
  Secuencia real de operacion: pipeline, benchmarks, sandbox, GraphDB espejo y fallback a `rdflib`.

- [operational_artifact_contract.md](operational_artifact_contract.md)
  Contrato de artefactos del carril operativo.

## Documentacion modular

- [src/6_extraction/README.md](..\src\6_extraction\README.md)
  Carril de construccion de A-Box y artefactos intermedios.

- [src/7_database/README.md](..\src\7_database\README.md)
  Backend RDF local, backend espejo GraphDB y herramientas de consulta/publicacion.

- [src/8_retrieval/README.md](..\src\8_retrieval\README.md)
  Retrieval, evaluacion formal y sandbox diagnostico.

- [src/9_rag_orchestrator/README.md](..\src\9_rag_orchestrator\README.md)
  Orquestacion conversacional final del runtime.

## Piezas transversales importantes

- GraphDB entra como backend espejo del grafo operativo ya materializado.
- `rdflib` sigue siendo el backend de referencia.
- Los benchmarks formales siguen separados del sandbox diagnostico.
- Los artefactos operativos y de evaluacion viven en `data/processed/`.
