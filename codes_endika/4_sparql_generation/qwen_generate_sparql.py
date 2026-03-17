# -*- coding: utf-8 -*-

import json
import re
from rdflib import Graph, RDFS, RDF, OWL
from rdflib.term import URIRef
from sentence_transformers import SentenceTransformer, util
import spacy

# QWEN LOCAL
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch


# ========================
# CONFIG
# ========================

QA_JSON = "qa_dataset_chunks.json"
ONTOLOGY_TTL = r"C:\Users\836582\Downloads\ontology_aligned.ttl"
OUTPUT_JSON = "qa_sparql_dataset.json"

TOP_K_CLASSES = 2
TOP_K_PROPERTIES = 2
MAX_TRIPLES = 20
MAX_CHARS = 3000


# ========================
# LOAD MODELS
# ========================

model_name = "Qwen/Qwen2.5-3B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model_llm = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float16,
    device_map="auto"
)

device = "cuda" if torch.cuda.is_available() else "cpu"

embed_model = SentenceTransformer("all-MiniLM-L6-v2")

nlp = spacy.load("es_core_news_sm")


# ========================
# TEXT CLEANING
# ========================

def clean_uri(uri):
    return uri.split("/")[-1].split("#")[-1]


def split_camel_case(text):
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", text)


def normalize_text(text):
    text = clean_uri(text)
    text = split_camel_case(text)
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


# ========================
# LOAD ONTOLOGY
# ========================

def load_ontology():

    g = Graph()
    g.parse(ONTOLOGY_TTL, format="ttl")

    classes = {}
    properties = {}
    uri_types = {}

    # detectar tipos RDF
    for s, p, o in g:
        if p == RDF.type:
            if o in (OWL.Class, RDFS.Class):
                uri_types[str(s)] = "class"
            elif o in (OWL.ObjectProperty, OWL.DatatypeProperty, RDF.Property):
                uri_types[str(s)] = "property"

    # labels + fallback
    for s, p, o in g:

        s_str = str(s)

        # usar label
        if p == RDFS.label and isinstance(s, URIRef):
            label = normalize_text(str(o))
            if len(label) > 2:
                if uri_types.get(s_str) == "property":
                    properties[label] = s_str
                else:
                    classes[label] = s_str

        # fallback URI limpia
        if isinstance(s, URIRef):
            clean = normalize_text(s_str)
            if len(clean) > 2:
                if uri_types.get(s_str) == "property":
                    properties[clean] = s_str
                else:
                    classes[clean] = s_str

    return g, classes, properties


# ========================
# NLP
# ========================

def extract_question_terms(question):

    doc = nlp(question)

    terms = set()

    for token in doc:
        if token.pos_ in ["NOUN", "PROPN"]:
            if not token.is_stop and len(token.text) > 2:
                terms.add(token.lemma_.lower())

    for chunk in doc.noun_chunks:

        words = [
            t.lemma_.lower()
            for t in chunk
            if not t.is_stop and t.pos_ in ["NOUN", "PROPN", "ADJ"]
        ]

        if len(words) >= 1:
            cleaned = " ".join(words)
            if len(cleaned.split()) <= 3:
                terms.add(cleaned)

    return list(terms)


# ========================
# SCHEMA LINKING
# ========================

def find_relevant_terms(question, classes, properties):

    q_terms = extract_question_terms(question)

    class_matches = set()
    prop_matches = set()

    class_keys = list(classes.keys())
    prop_keys = list(properties.keys())

    class_emb = embed_model.encode(class_keys, convert_to_tensor=True)
    prop_emb = embed_model.encode(prop_keys, convert_to_tensor=True)

    for q in q_terms:

        q_emb = embed_model.encode(q, convert_to_tensor=True)

        # clases
        scores_c = util.cos_sim(q_emb, class_emb)[0]
        for i in scores_c.argsort(descending=True)[:TOP_K_CLASSES]:
            class_matches.add(classes[class_keys[i]])

        # propiedades
        scores_p = util.cos_sim(q_emb, prop_emb)[0]
        for i in scores_p.argsort(descending=True)[:TOP_K_PROPERTIES]:
            prop_matches.add(properties[prop_keys[i]])

    # filtrar ruido RDF/OWL
    def clean_uris(uris):
        return [
            u for u in uris
            if not any(x in u.lower() for x in ["rdf", "owl", "xmlschema"])
        ]

    return clean_uris(list(class_matches | prop_matches))


# ========================
# SUBGRAPH
# ========================

def extract_subgraph(graph, relevant_uris):

    triples = []

    for s, p, o in graph:
        if str(s) in relevant_uris or str(p) in relevant_uris or str(o) in relevant_uris:
            triples.append((s, p, o))

    def score(triple):
        s, p, o = triple
        return sum([
            str(s) in relevant_uris,
            str(p) in relevant_uris,
            str(o) in relevant_uris
        ])

    triples = sorted(triples, key=score, reverse=True)[:MAX_TRIPLES]

    ttl = ""
    for s, p, o in triples:
        ttl += f"<{s}> <{p}> <{o}> .\n"

    if len(ttl) > MAX_CHARS:
        ttl = ttl[:MAX_CHARS]

    return ttl


# ========================
# PROMPT
# ========================

def build_prompt(question, subgraph):

    return f"""
You are a strict SPARQL generator.

Ontology:
{subgraph}

STRICT RULES:
- Use ONLY provided URIs
- DO NOT explain
- DO NOT infer
- DO NOT add text
- DO NOT add markdown
- DO NOT describe anything
- ONLY output SPARQL query
- If answer cannot be built, return EMPTY QUERY

OUTPUT FORMAT (STRICT):

<SPARQL>
SELECT ... 
</SPARQL>

QUESTION:
{question}
"""


# ========================
# QWEN
# ========================

def call_qwen(prompt):

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=4096
    ).to(device)

    outputs = model_llm.generate(
        **inputs,
        max_new_tokens=512,
        temperature=0.0,  # 🔥 importante
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id
    )

    modelol=tokenizer.decode(outputs[0], skip_special_tokens=True)
    print(modelol)

    return modelol


# ========================
# PARSE SPARQL
# ========================

def extract_sparql(text):

    matches = re.findall(r"<SPARQL>(.*?)</SPARQL>", text, re.DOTALL)

    if matches:
        return matches[-1].strip()

    return ""


# ========================
# MAIN
# ========================

def main():

    qa_data = json.load(open(QA_JSON, encoding="utf-8"))

    graph, classes, properties = load_ontology()

    results = []

    for chunk in qa_data:

        chunk_out = {
            "chunk_id": chunk["chunk_id"],
            "questions": []
        }

        for q in chunk["questions"]:

            question = q["question"]

            relevant_uris = find_relevant_terms(question, classes, properties)

            subgraph = extract_subgraph(graph, relevant_uris)

            prompt = build_prompt(question, subgraph)

            response = call_qwen(prompt)

            sparql = extract_sparql(response)

            chunk_out["questions"].append({
                "question": question,
                "answer": q["answer"],
                "sparql": sparql
            })

            print("\n--------------------------------")
            print("QUESTION:", question)
            print("\nMATCHED URIS:", relevant_uris)
            print("\nSPARQL:\n", sparql)
            print("--------------------------------\n")

        results.append(chunk_out)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


# ========================
# RUN
# ========================

if __name__ == "__main__":
    main()