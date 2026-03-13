# Evaluation Dataset Generation from Technical Manuals

This module implements **Task 4: Evaluation Dataset Generation** of the ontology-based QA pipeline.

The goal is to automatically generate **semantic questions and reference answers** from fragments of a technical manual.  
These question–answer pairs are used as a **gold evaluation dataset** for assessing a semantic question answering system operating over an ontology.

The dataset is generated using a **Large Language Model (LLM)** guided by a structured prompt and strict anti-hallucination rules.

---

# Overview

The system generates evaluation data from manual fragments (*chunks*).

For each chunk:

1. The text fragment is analyzed.
2. Entities and factual information are identified.
3. Semantic questions are generated.
4. Correct answers are extracted directly from the text.
5. The result is stored as a structured JSON dataset.

The number of generated questions depends on the **information density of the chunk**.

---

# Dataset Generation Strategy

The dataset is generated according to the following principles:

- Questions must be **grounded strictly in the text**.
- Answers must correspond to **explicit information present in the chunk**.
- External knowledge is **not allowed**.
- The dataset must reflect the **semantic structure of the manual**.

This ensures that the generated dataset can be used as a **reliable benchmark for ontology-based question answering systems**.

---

# Question Types

Questions are generated across different semantic categories:

- factual questions about machines
- component relationships
- document structure information
- technical attributes
- manufacturer or model information
- references to figures or sections

---

# Number of Questions per Chunk

The number of generated questions depends on the **information density** of the chunk.

| Information Density | Questions Generated |
|--------------------|--------------------|
| Low density | 1–2 questions |
| Medium density | 2–3 questions |
| High density | 4–5 questions |

At least **one question must be generated** if the chunk contains factual information.

---

# Anti-Hallucination Rules

To ensure dataset reliability, strict constraints are applied:

- Only information **explicitly present in the text** may be used.
- No external knowledge may be introduced.
- Missing information must **not be inferred**.
- Questions must not rely on implicit assumptions.

If a fact does not appear explicitly in the text, **no question should be generated about it**.

---

# Output Format

The generated dataset follows a strict JSON schema:

```json
{
  "chunk_summary": "",
  "questions": [
    {
      "question": "",
      "answer": ""
    }
  ]
}
