# QA Dataset Generation from Technical Manual Chunks

This script automatically generates a **Question–Answer (QA) evaluation dataset** from chunks of a technical manual using the **Mistral LLM API**.

The generated dataset is intended to evaluate **semantic question answering systems over knowledge graphs** built from the manual.

---

# Overview

The script performs the following steps:

1. Reads a `.txt` file containing **text chunks extracted from a technical manual**.
2. Splits the document into chunks using a predefined header pattern.
3. Sends each chunk to **Mistral (`mistral-small-latest`)** with a structured prompt.
4. The model generates **questions and answers grounded strictly in the chunk**.
5. The results are stored incrementally in a **JSON dataset**.

Each chunk produces **1–5 QA pairs depending on the information density** of the text.

---

# Output

The script generates a JSON file:

Example structure:

```json
[
  {
    "chunk_id": 1,
    "chunk_summary": "Description of the broaching machine model A218.",
    "questions": [
      {
        "question": "What is the model name of the broaching machine?",
        "answer": "A218/RASHEM 7x3000x500"
      }
    ]
  }
]```
