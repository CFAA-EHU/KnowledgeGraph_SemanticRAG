# Ontology Extraction from Technical Manuals using LLMs

This project implements an **LLM-based pipeline for automatic ontology extraction** from technical manuals.  
The system processes document fragments (*chunks*), extracts semantic knowledge using a **Large Language Model (Mistral)**, and converts it into a structured **RDF/OWL ontology serialized in Turtle (TTL)**.

The pipeline follows a **chunk-based ontology learning approach** with strong anti-hallucination constraints and ontology normalization rules.

---

# Overview

The system performs the following steps:

1. **Chunk Processing**
   - The technical manual is split into fragments.
   - Each fragment is processed independently.

2. **Ontology Extraction (LLM)**
   - A prompt guides the LLM through a structured reasoning process.
   - The model extracts:
     - classes
     - object properties
     - datatype properties
     - instances
     - relations

3. **Structured JSON Output**
   - The LLM returns ontology elements in a strict JSON schema.

4. **RDF Conversion**
   - JSON elements are converted to RDF triples using **rdflib**.

5. **Ontology Aggregation**
   - Fragment graphs are merged into a **global ontology graph**.

6. **Serialization**
   - The final ontology is exported as a **Turtle (.ttl) file**.

---

# Architecture

Pipeline workflow:

Technical Manual
│
▼
Chunk Extraction
│
▼
LLM Ontology Extraction
│
▼
Structured JSON
│
▼
RDF Graph Construction
│
▼
Fragment Graph Merge
│
▼
Final Ontology (TTL)


---

# Features

- **LLM-driven ontology learning**
- **Chain-of-Thought reasoning prompt**
- **Anti-hallucination constraints**
- **Strict ontology schema generation**
- **Automatic RDF graph construction**
- **Incremental ontology merging**
- **Multilingual labels (Spanish / English)**

---

# Ontology Schema

The ontology elements extracted include:

### Classes
General domain concepts.

Example:


Machine
Manual
Company
SafetyInstruction

---

### Object Properties
Relationships between entities.

Example:


hasManual
hasManufacturer
containsSection


---

### Datatype Properties
Attributes of entities.

Example:


hasEmail
hasPhone
hasModel
hasYear


---

### Instances
Specific real-world entities appearing in the manual.

Example:


EKIN
A218
ManualA218


---

# Prompt Engineering Strategy

The LLM prompt enforces a **structured reasoning process**:

1. Context understanding  
2. Entity identification  
3. Concept classification  
4. Relationship extraction  
5. Ontology validation  

Anti-hallucination rules ensure that:

- Only entities appearing in the text are extracted
- No artificial hierarchies are generated
- Missing information is not guessed

---

| File | Description |
|-----|-------------|
| `ontology_extraction.py` | Main ontology extraction script |
| `chunks_b.txt` | Input text fragments from the manual |
| `ontology_3.ttl` | Generated ontology |
| `README.md` | Project documentation |
