# -*- coding: utf-8 -*-

import json
import re
import time
from pathlib import Path
from mistralai import Mistral

#API_KEY = "HMXKoCPyStwJ9DjLnGQbKYMg2KqCiEUs"
API_KEY = "GbcXSJsUQXXNpm4hubVn46alL4tJ35KU"

MODEL = "mistral-small-latest"

INPUT_FILE = "C:\\Users\\836582\\Downloads\\chunks_manual_instrucciones_a218.txt"
OUTPUT_FILE = "qa_dataset_chunks.json"

client = Mistral(api_key=API_KEY)


def parse_chunks(filepath):

    text = Path(filepath).read_text(encoding="utf-8")

    header_pattern = re.compile(
        r"---\s*Páginas:\s*\[.*?\]\s*\|\s*Sección:\s*.*?\s*\|\s*Título:\s*.*?\s*---"
    )

    parts = header_pattern.split(text)

    chunks = [p.strip() for p in parts if p.strip()]

    return chunks


def build_prompt(chunk_text):

    prompt = f"""
You are an expert in technical documentation analysis and knowledge graph evaluation.

Your task is to generate an evaluation dataset from a fragment (chunk) of a technical manual.

The dataset will be used to evaluate a semantic question answering system over an ontology extracted from the manual.

IMPORTANT:
The questions and answers must be strictly grounded in the provided text.

Do NOT invent information.
Do NOT use external knowledge.

--------------------------------
TASK
--------------------------------

You will receive ONE chunk of text extracted from a technical manual.

For EACH chunk you must:

1. Identify the entities and factual information contained in the text.

2. Determine the information density of the chunk.

3. Generate a set of semantic questions that could be answered using a knowledge graph derived from this chunk.

4. For each generated question, provide the correct answer strictly based on the text.

5. The answers must correspond ONLY to explicit information present in the text.

--------------------------------
QUESTION TYPES
--------------------------------

Generate questions of different types, such as:

• factual questions about machines  
• component relationships  
• document structure information  
• technical attributes  
• manufacturer or model information  
• references to figures or sections  

--------------------------------
NUMBER OF QUESTIONS PER CHUNK
--------------------------------

For EACH chunk you MUST generate a number of questions proportional to the information density of the text:

Low density → 1–2 questions  
Medium density → 2–3 questions  
High density → 4–5 questions  

Always generate at least ONE question if the chunk contains any factual information.

--------------------------------
ANTI-HALLUCINATION RULES
--------------------------------

STRICT RULES:

- Use ONLY information explicitly present in the text.
- Do NOT infer missing knowledge.
- Do NOT use external knowledge.
- Do NOT reformulate answers with information not present in the text.
- If a fact is not explicitly written in the text, do not generate a question about it.

--------------------------------
ANSWER RULES
--------------------------------

The answer must be:

• concise  
• factual  
• directly supported by the text  
• suitable as a gold reference answer for evaluation  

--------------------------------
OUTPUT FORMAT
--------------------------------

Return ONLY valid JSON.

Structure:

{{
  "chunk_summary": "",
  "questions": [
    {{
      "question": "",
      "answer": ""
    }}
  ]
}}

--------------------------------
VALIDATION BEFORE OUTPUT
--------------------------------

Before producing the final output:

1. Verify that every answer is explicitly supported by the text.
2. Remove questions whose answers require inference.
3. Ensure that questions correspond to facts that could be represented in a knowledge graph.

--------------------------------
TEXT CHUNK
--------------------------------

{chunk_text}
"""

    return prompt


def call_mistral(prompt):

    response = client.chat.complete(
        model=MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content


def extract_json(text):

    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except:
        pass

    return {
        "chunk_summary": "",
        "questions": []
    }


def save_progress(data):

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():

    chunks = parse_chunks(INPUT_FILE)

    results = []

    print(f"\nChunks detectados: {len(chunks)}\n")

    for i, chunk in enumerate(chunks):

        print(f"Procesando chunk {i+1}/{len(chunks)}")

        prompt = build_prompt(chunk)

        try:

            response = call_mistral(prompt)

            parsed = extract_json(response)

            entry = {
                "chunk_id": i + 1,
                "chunk_summary": parsed.get("chunk_summary", ""),
                "questions": parsed.get("questions", [])
            }

            results.append(entry)

            save_progress(results)

            print(f"   preguntas generadas: {len(entry['questions'])}")

        except Exception as e:

            print(f"   error en chunk {i+1}: {e}")

        time.sleep(1)

    print("\nDataset generado:", OUTPUT_FILE)


if __name__ == "__main__":
    main()