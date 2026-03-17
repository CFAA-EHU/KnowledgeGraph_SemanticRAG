# SPARQL Query Generation from QA Dataset using Ontology Subgraphs

This script generates **SPARQL queries automatically from a QA dataset** using a combination of:

- **Ontology parsing (RDF/TTL)**
- **Semantic similarity (SentenceTransformers)**
- **Subgraph extraction (schema linking)**
- **Mistral LLM for SPARQL generation**

The goal is to transform natural language questions into **valid SPARQL queries grounded in an ontology**.

---

# Overview

The script performs the following pipeline:

1. Loads a **QA dataset** (questions + answers).
2. Loads an **ontology in Turtle format (`.ttl`)**.
3. For each question:
   - Computes semantic similarity with ontology terms.
   - Selects the most relevant terms (**schema linking**).
   - Extracts a **subgraph of relevant triples**.
   - Sends the subgraph + question to **Mistral**.
   - Generates a **SPARQL query**.
4. Stores results in a new JSON file.

---

# Input

A JSON file (QA Dataset) like:

```json
[
  {
    "chunk_id": 1,
    "questions": [
      {
        "question": "What is the model name of the machine?",
        "answer": "A218/RASHEM 7x3000x500"
      }
    ]
  }
]
```

---

# Output

```json
[
  {
    "chunk_id": 1,
    "questions": [
      {
        "question": "What is the model name of the machine?",
        "answer": "A218/RASHEM 7x3000x500",
        "sparql": "SELECT ?model WHERE { ?machine :modelName ?model . }"
      }
    ]
  }
]
```
