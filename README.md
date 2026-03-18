# KnowledgeGraph_SemanticRAG

Pipeline experimental y operativo para convertir manuales técnicos industriales en un knowledge graph RDF/OWL consultable con SPARQL, y usar ese grafo como base de un Semantic RAG trazable.

El caso de uso actual es el manual de la brochadora electromecánica **A218 / RASHEM - 7x3000x500**. El objetivo ya no es una extracción abierta de ontología, sino un carril operativo estable basado en:

- **T-Box canónica fija**
- **extracción A-Box restringida**
- **consulta SPARQL guiada por intención**
- **evaluación reproducible**
- **validación de queryability, boundedness y multi-hop**

---

## Estado actual del proyecto

El repositorio contiene **dos carriles**:

### Carril operativo
Es el flujo por defecto del proyecto y el único que debe usarse para build, consulta y evaluación actuales.

- **T-Box operativa:** `data/processed/ontology_aligned.ttl`
- **Input operativo A-Box:** `data/processed/abox_input.json`
- **A-Box operativa:** `data/processed/abox_merged.ttl`
- **Schema condensado:** `data/processed/schema_condensed.txt`
- **Dataset canónico de evaluación:** `data/golden_set/QA_canonical.json`

### Carril experimental
Se conserva para investigación y prototipado, pero ya no define el flujo principal.

Ejemplos:
- `data/processed/tbox_prompts.json`
- `data/processed/ontology_merged.ttl`
- `data/processed/abox_aligned.ttl`

---

## Arquitectura actual

```text
Manual técnico
   │
   ├── Tarea 1: Ingesta y chunking semántico
   │      └── data/raw/density_report.json
   │
   ├── Tarea 2: Carril experimental T-Box
   │      ├── src/2_extraction/prompt_assembler.py
   │      └── src/2_extraction/llm_extractor.py
   │
   ├── Tarea 3–5: Consolidación / validación / alineamiento experimental
   │
   ├── Tarea 6: Extracción A-Box operativa
   │      ├── src/6_extraction/abox_input_builder.py
   │      ├── src/6_extraction/abox_extractor.py
   │      ├── src/6_extraction/abox_resume_policy.py
   │      ├── src/6_extraction/abox_ttl_validator.py
   │      ├── src/6_extraction/abox_semantic_validator.py
   │      └── src/6_extraction/abox_merger.py
   │
   ├── Tarea 7: Store SPARQL embebido
   │      └── src/7_database/embedded_store.py
   │
   ├── Tarea 8: Retrieval y evaluación
   │      ├── src/8_retrieval/schema_condenser.py
   │      ├── src/8_retrieval/text_to_sparql.py
   │      └── src/8_retrieval/qa_evaluator.py
   │
   ├── Tarea 9: Orquestación RAG
   │      └── src/9_rag_orchestrator/semantic_rag.py
   │
   └── Tarea 10–11: Planner compartido, suite SPARQL canónica y validación multi-hop
          ├── data/processed/query_intent_catalog.json
          ├── data/processed/query_debug_report.json
          ├── data/processed/queryability_target_matrix.json
          ├── data/processed/ontology_queryability_audit.json
          ├── data/processed/canonical_sparql_suite.json
          ├── data/processed/canonical_sparql_execution_report.json
          ├── data/processed/canonical_vs_generated_comparison.json
          ├── data/golden_set/QA_multihop.json
          └── query_workbench.py