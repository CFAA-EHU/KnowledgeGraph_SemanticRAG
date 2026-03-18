# KnowledgeGraph_SemanticRAG

Pipeline experimental y operativo para transformar manuales técnicos industriales en un knowledge graph RDF/OWL consultable con SPARQL y usar ese grafo como base de un Semantic RAG trazable.

El caso de uso actual es el manual de la brochadora electromecánica **A218 / RASHEM - 7x3000x500**.

---

## Estado actual del proyecto

El repositorio mantiene dos carriles:

### Carril operativo
Es el flujo oficial para build, consulta y evaluación.

Artefactos canónicos:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_input.json`
- `data/processed/abox_merged.ttl`
- `data/processed/schema_condensed.txt`
- `data/golden_set/QA_canonical.json`

### Carril experimental
Se conserva para investigación y comparación, pero no define el flujo principal.

Ejemplos:
- `data/processed/tbox_prompts.json`
- `data/processed/ontology_merged.ttl`
- `data/processed/abox_aligned.ttl`

---

## Arquitectura actual

Manual técnico
   │
   ├── 1_ingestion
   │      └── density_report.json
   │
   ├── 2_extraction (experimental T-Box)
   │      ├── prompt_assembler.py
   │      └── llm_extractor.py
   │
   ├── 5_alignment (experimental)
   │      └── semantic_reduction.py
   │
   ├── 6_extraction (operativo A-Box)
   │      ├── abox_input_builder.py
   │      ├── abox_extractor.py
   │      ├── abox_resume_policy.py
   │      ├── abox_ttl_validator.py
   │      ├── abox_semantic_validator.py
   │      └── abox_merger.py
   │
   ├── 7_database
   │      └── embedded_store.py
   │
   ├── 8_retrieval
   │      ├── schema_condenser.py
   │      ├── text_to_sparql.py
   │      └── qa_evaluator.py
   │
   ├── 9_rag_orchestrator
   │      └── semantic_rag.py
   │
   └── query_workbench.py

## Build operativo

El entrypoint oficial del build es:
- `python run_operational_pipeline.py --mode resume-compatible`

Modos disponibles:

- resume-compatible
- force-stale
- force-all

Este flujo ejecuta:

- 'src/6_extraction/abox_input_builder.py'
- 'src/6_extraction/abox_extractor.py'
- 'src/6_extraction/abox_merger.py'

## Query layer actual

El query layer compartido vive en:

'src/8_retrieval/text_to_sparql.py'

## Estado tras T12:

- expone planes de consulta explícitos
- soporta 1, 2 y 3 hops
- usa familias multi-hop validadas
- ejecuta recuperación por pasos
- controla boundedness por salto
- deja trazabilidad completa de ejecución
- funciona como capa compartida entre:

>> src/8_retrieval/qa_evaluator.py
>> src/9_rag_orchestrator/semantic_rag.py
>> query_workbench.py

## Queryability y SPARQL canónica

La validación de queryability del grafo quedó persistida en:
- 'data/processed/queryability_target_matrix.json'
- 'data/processed/ontology_queryability_audit.json'
- 'data/processed/canonical_sparql_suite.json'
- 'data/processed/canonical_sparql_execution_report.json'
- 'data/processed/canonical_vs_generated_comparison.json'

Resultado actual:

- el grafo soporta consultas bounded y usable de 1, 2 y 3 hops
- la suite canónica validó 11 consultas
- el benchmark multi-hop validó 7/7 preguntas
- el siguiente cuello de botella ya no es ontología, sino generalización del planner fuera de las familias seedadas

## Workbench para preguntas nuevas

Existe una herramienta de inspección manual en:

- 'query_workbench.py'

Permite ver:
- intención detectada
- ancla detectada
- hop previsto
- familia/plantilla elegida
- queries por paso
- resultados crudos
- boundedness y fallback si aplica

Uso típico:

- 'python query_workbench.py'

## Contratos y documentación

La fuente única de verdad de rutas y artefactos es:

- 'artifact_contracts.py'

Documentación complementaria:

- docs/operational_artifact_contract.md
- docs/operational_pipeline_runbook.md