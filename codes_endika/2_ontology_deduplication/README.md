# Ontology Integration and Refinement using Semantic Alignment and LLM Validation

This module implements **Graph Synthesis and Integration** of the ontology learning pipeline.

Starting from the ontology generated before, the system performs:

- semantic deduplication of entities
- ontology merging
- structural validation using an LLM
- automatic ontology repair

The result is a **clean, consolidated and consistent ontology**.

Input ontology fragments are merged and refined into a **single coherent knowledge graph**.

---

# Overview

The pipeline processes an existing ontology and performs several refinement steps.

1. **Ontology Loading**
   - The ontology generated in Task 2 is loaded from a TTL file.

2. **Entity Detection**
   - Classes
   - Object properties
   - Datatype properties
   - Individuals

3. **Semantic Deduplication**
   - Entity labels are embedded using **Sentence Transformers**
   - Cosine similarity is used to detect semantic duplicates
   - Similar entities are merged automatically

4. **Graph Merging**
   - Triples referencing duplicate entities are rewritten using a representative URI.

5. **Ontology Consistency Check**
   - The ontology is analyzed by an **LLM validator**
   - Structural problems are detected.

6. **Automatic Repair**
   - Redundant classes are merged
   - Invalid triples are removed

7. **Final Ontology Export**
   - The refined ontology is saved as a new **Turtle (.ttl)** file.

---

# Architecture

Pipeline workflow:

Initial Ontology (Task 2) --> Ontology Loading --> Entity Detection --> Semantic Deduplication (Embeddings) --> Entity Merging --> Ontology Consistency Check (LLM) --> Automatic Ontology Repair --> Final Refined Ontology (TTL)

---

# Features

- **Semantic entity alignment using embeddings**
- **Automatic ontology deduplication**
- **Cycle-safe entity merging**
- **LLM-based ontology validation**
- **Automatic ontology repair**
- **Improved ontology coherence**

---

# Project Structure


| File | Description |
|-----|-------------|
| `ontology_deduplication.py` | Ontology synthesis and refinement pipeline |
| `ontology_merged.ttl` | Ontology generated in Task 1 |
| `deduplicated_ontology.ttl` | Final refined ontology |
| `README.md` | Documentation |
