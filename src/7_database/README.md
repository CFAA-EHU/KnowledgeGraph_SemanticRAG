
---

## 5) `c:\Users\Leonardo\Documents\00 Projects\Activos\2026 SemanticOnt\KnowledgeGraph_SemanticRAG\src\7_database\README.md`

```markdown
# src/7_database — Store RDF embebido y ejecución SPARQL

Este directorio contiene el runtime mínimo de carga y consulta del knowledge graph operativo.

## Script principal

### `embedded_store.py`
Carga en memoria:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_merged.ttl`

y expone ejecución SPARQL sobre el grafo combinado.

## Objetivo
Servir como backend simple para:
- validación manual de consultas SPARQL
- retrieval automático
- evaluación
- smoke tests del runtime

## Garantía de contrato
El store solo debe consumir artefactos canónicos del carril operativo:
- `ontology_aligned.ttl`
- `abox_merged.ttl`

No debe consumir artefactos experimentales.

## Uso típico
- comprobar que el grafo carga correctamente
- ejecutar consultas de depuración
- servir de base a `qa_evaluator.py`
- servir de base a `semantic_rag.py`
- probar la suite de consultas SPARQL canónicas

## Estado actual
Tras T11, el store ya soporta:
- consultas canónicas bounded
- rutas de 1, 2 y 3 hops verificadas
- validación práctica de queryability sobre el grafo operativo