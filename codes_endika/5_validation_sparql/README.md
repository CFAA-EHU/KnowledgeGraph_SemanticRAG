# Semantic Query Interface (SPARQL)

## Overview

This module implements the **semantic query interface** of the ontology-based QA pipeline.  
Its goal is to translate **natural language questions into SPARQL queries** and validate that the queries are **syntactically correct, semantically aligned with the ontology, and faithful to the user’s intent**.

The system combines **LLM-based SPARQL generation** with **deterministic validation over the ontology schema**.

---

## Pipeline

The validation pipeline follows these steps:

User Question --> SPARQL Generation (LLM) --> T-Box Validation --> Domain / Range Validation --> SPARQL Back Translation --> Cosine Similarity Validation --> Validated SPARQL Query

---

## Output

The pipeline determines whether a generated SPARQL query is **valid or rejected** based on:

- Ontology schema alignment
- Domain/range consistency
- Semantic similarity with the original question

---

## Example

```python
question = "What model does the A218 machine have?"

sparql_query = """
PREFIX ex: <https://vocab.cfaa.eus/broaching/>

SELECT ?model
WHERE {
    ex:A218 ex:hasModel ?model .
}
"""
