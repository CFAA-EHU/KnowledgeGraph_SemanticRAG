# -*- coding: utf-8 -*-

import json
import re
from pathlib import Path
from rdflib import Graph
from sentence_transformers import SentenceTransformer, util
from mistralai import Mistral

API_KEY = "GbcXSJsUQXXNpm4hubVn46alL4tJ35KU"
MODEL = "mistral-small-latest"

QA_JSON = "qa_dataset_chunks.json"
ONTOLOGY_TTL = "C:\\Users\\836582\\Downloads\\ontology_aligned.ttl"
OUTPUT_JSON = "qa_sparql_dataset.json"

TOP_K = 6

client = Mistral(api_key=API_KEY)
model = SentenceTransformer("all-MiniLM-L6-v2")


def load_ontology():

    g = Graph()
    g.parse(ONTOLOGY_TTL, format="ttl")

    terms = []

    for s, p, o in g:

        s = str(s)
        p = str(p)
        o = str(o)

        terms.append(s)
        terms.append(p)
        terms.append(o)

    terms = list(set(terms))

    return g, terms


def find_relevant_terms(question, ontology_terms):

    q_emb = model.encode(question, convert_to_tensor=True)

    term_emb = model.encode(ontology_terms, convert_to_tensor=True)

    scores = util.cos_sim(q_emb, term_emb)[0]

    top_idx = scores.argsort(descending=True)[:TOP_K]

    return [ontology_terms[i] for i in top_idx]


def extract_subgraph(graph, terms):

    triples = []

    for s, p, o in graph:

        if str(s) in terms or str(p) in terms or str(o) in terms:
            triples.append((s, p, o))

    ttl = ""

    for s, p, o in triples:
        ttl += f"<{s}> <{p}> <{o}> .\n"

    return ttl


def build_prompt(question, subgraph):

    prompt = f"""
You are a SPARQL query generator.

Ontology subset (Turtle):
-------------------------
{subgraph}

Rules:
- Use ONLY entities and relations present in the ontology subset.
- Respect relation direction.
- Do NOT invent identifiers.
- Return ONLY the query inside <SPARQL> tags.
- No explanations.

User question:
{question}

Answer format:

<SPARQL>
SELECT ...
WHERE {{
 ...
}}
</SPARQL>
"""

    return prompt


def call_mistral(prompt):

    response = client.chat.complete(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )

    return response.choices[0].message.content


def extract_sparql(text):

    match = re.search(r"<SPARQL>(.*?)</SPARQL>", text, re.DOTALL)

    if match:
        return match.group(1).strip()

    return ""


def main():

    qa_data = json.load(open(QA_JSON, encoding="utf-8"))

    graph, ontology_terms = load_ontology()

    results = []

    for chunk in qa_data:

        chunk_out = {
            "chunk_id": chunk["chunk_id"],
            "questions": []
        }

        for q in chunk["questions"]:
            question = q["question"]

            relevant_terms = find_relevant_terms(question, ontology_terms)

            subgraph = extract_subgraph(graph, relevant_terms)

            prompt = build_prompt(question, subgraph)

            response = call_mistral(prompt)

            sparql = extract_sparql(response)

            chunk_out["questions"].append({
                "question": question,
                "answer": q["answer"],
                "sparql": sparql
            })

            print("\n--------------------------------")
            print("QUESTION:")
            print(question)

            print("\nGENERATED SPARQL:")
            print(sparql)
            print("--------------------------------\n")

        results.append(chunk_out)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()