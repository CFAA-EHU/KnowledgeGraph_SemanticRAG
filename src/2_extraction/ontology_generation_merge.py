import os
import json
import re
from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, XSD
from mistralai import Mistral

############################################
# CONFIG
############################################

API_KEY = "MISTRAL_API_KEY"
MODEL = "mistral-small-latest"

INPUT_FILE = "chunks_b.txt"
OUTPUT_ONTOLOGY = "ontology_3.ttl"

client = Mistral(api_key=API_KEY)

EX = Namespace("https://vocab.cfaa.eus/broaching/")

############################################
# PROMPT
############################################

ONTOLOGY_PROMPT = """
You are an expert ontology engineer and semantic web specialist.

Your task is to extract ontology knowledge from a technical manual fragment.

IMPORTANT: Work ONLY with the information explicitly present in the text.

You must internally follow these reasoning steps:

Step 1 — Context understanding
Read the text carefully and determine the technical context of the fragment.

Step 2 — Entity identification
Identify ONLY the entities that explicitly appear in the text:
- machines
- components
- documents
- companies
- technical elements
- processes

List them mentally before generating the ontology.

Step 3 — Concept classification
Determine which entities correspond to:
- Classes (general concepts)
- Instances (specific real entities)
- Object properties (relations between entities)
- Datatype properties (attributes such as email, phone, model, number, etc.)

Step 4 — Relationship extraction
Identify relationships that are explicitly described in the text.
Create relations ONLY if they are clearly supported by the text.

Step 5 — Validation
Before producing the output ensure:
- No duplicated entities
- All URIs are consistent
- All properties have domain and range
- Instances belong to an existing class
- No invented information

STRICT ANTI-HALLUCINATION RULES:

- NEVER invent classes
- NEVER invent properties
- NEVER infer hierarchy not present in the text
- NEVER create relations not explicitly supported
- If information is missing, simply omit it
- Do not guess missing domains or ranges

NAMING RULES:

Classes:
CamelCase

Examples:
Machine
Manual
Company
SafetyInstruction

Object properties:
camelCase

Examples:
hasManual
hasManufacturer
containsSection

Datatype properties:
camelCase

Examples:
hasEmail
hasPhone
hasModel
hasYear

INSTANCE RULES:

Instances must represent real objects appearing in the text:
Examples:
EKIN
A218
ManualA218

OUTPUT FORMAT:

Return ONLY valid JSON with EXACTLY this structure:

{
  "classes": [
    {
      "id": "",
      "label_es": "",
      "label_en": ""
    }
  ],
  "object_properties": [
    {
      "id": "",
      "label_es": "",
      "label_en": "",
      "domain": "",
      "range": ""
    }
  ],
  "datatype_properties": [
    {
      "id": "",
      "label_es": "",
      "label_en": "",
      "domain": "",
      "datatype": ""
    }
  ],
  "class_relations": [
    {
      "subject": "",
      "predicate": "",
      "object": ""
    }
  ],
  "instances": [
    {
      "id": "",
      "type": "",
      "label": ""
    }
  ],
  "instance_object_relations": [
    {
      "subject": "",
      "predicate": "",
      "object": ""
    }
  ],
  "instance_data_relations": [
    {
      "subject": "",
      "predicate": "",
      "value": "",
      "datatype": ""
    }
  ]
}

CRITICAL OUTPUT RULES:

- Return ONLY JSON
- No explanations
- No markdown
- No comments
- No text outside JSON

TEXT TO PROCESS:
"""

############################################
# LLM CALL
############################################

def ask_llm(prompt):

    response = client.chat.complete(
        model=MODEL,
        messages=[{"role":"user","content":prompt}]
    )

    return response.choices[0].message.content


############################################
# LOAD CHUNKS
############################################

def load_chunks(file):

    text = open(file, encoding="utf-8").read()

    chunks = re.split(r"--- Páginas:.*?---", text)

    chunks = [c.strip() for c in chunks if len(c.strip()) > 50]

    print("Chunks detected:", len(chunks))

    return chunks


############################################
# JSON → RDF
############################################

def json_to_rdf(data, graph):

    ########################################
    # CLASSES
    ########################################

    for c in data.get("classes",[]):

        uri = EX[c["id"]]

        graph.add((uri, RDF.type, OWL.Class))
        graph.add((uri, RDFS.label, Literal(c["label_es"], lang="es")))
        graph.add((uri, RDFS.label, Literal(c["label_en"], lang="en")))

    ########################################
    # OBJECT PROPERTIES
    ########################################

    for p in data.get("object_properties",[]):

        uri = EX[p["id"]]

        graph.add((uri, RDF.type, OWL.ObjectProperty))

        graph.add((uri, RDFS.label, Literal(p["label_es"], lang="es")))
        graph.add((uri, RDFS.label, Literal(p["label_en"], lang="en")))

        graph.add((uri, RDFS.domain, EX[p["domain"]]))
        graph.add((uri, RDFS.range, EX[p["range"]]))

    ########################################
    # DATATYPE PROPERTIES
    ########################################

    for p in data.get("datatype_properties",[]):

        uri = EX[p["id"]]

        graph.add((uri, RDF.type, OWL.DatatypeProperty))

        graph.add((uri, RDFS.label, Literal(p["label_es"], lang="es")))
        graph.add((uri, RDFS.label, Literal(p["label_en"], lang="en")))

        graph.add((uri, RDFS.domain, EX[p["domain"]]))

    ########################################
    # CLASS RELATIONS
    ########################################

    for r in data.get("class_relations",[]):

        graph.add((
            EX[r["subject"]],
            EX[r["predicate"]],
            EX[r["object"]]
        ))

    ########################################
    # INSTANCES
    ########################################

    for inst in data.get("instances",[]):

        uri = EX[inst["id"]]

        graph.add((uri, RDF.type, EX[inst["type"]]))
        graph.add((uri, RDFS.label, Literal(inst["label"])))

    ########################################
    # INSTANCE OBJECT RELATIONS
    ########################################

    for r in data.get("instance_object_relations",[]):

        graph.add((
            EX[r["subject"]],
            EX[r["predicate"]],
            EX[r["object"]]
        ))

    ########################################
    # INSTANCE DATA RELATIONS
    ########################################

    datatype_map = {
        "string": XSD.string,
        "integer": XSD.integer,
        "float": XSD.float,
        "year": XSD.gYear
    }

    for r in data.get("instance_data_relations",[]):

        dt = datatype_map.get(r["datatype"], XSD.string)

        graph.add((
            EX[r["subject"]],
            EX[r["predicate"]],
            Literal(r["value"], datatype=dt)
        ))


############################################
# PROCESS CHUNK
############################################

def process_chunk(chunk):

    prompt = ONTOLOGY_PROMPT + chunk

    response = ask_llm(prompt)

    response = response.replace("```json","").replace("```","")

    try:
        data = json.loads(response)
        return data
    except:

        print("Invalid JSON returned by LLM")
        print(response)

        return None


############################################
# BUILD ONTOLOGY
############################################

def build_ontology(chunks):

    global_graph = Graph()
    global_graph.bind("ex", EX)

    for i, chunk in enumerate(chunks):

        print("\n=============================")
        print("PROCESSING CHUNK", i+1)
        print("=============================\n")

        data = process_chunk(chunk)

        if not data:
            continue

        chunk_graph = Graph()
        chunk_graph.bind("ex", EX)

        json_to_rdf(data, chunk_graph)

        print("Ontology generated for this chunk:\n")
        print(chunk_graph.serialize(format="turtle"))

        for triple in chunk_graph:
            global_graph.add(triple)

    return global_graph


############################################
# MAIN
############################################

def main():

    chunks = load_chunks(INPUT_FILE)

    graph = build_ontology(chunks)

    graph.serialize(OUTPUT_ONTOLOGY, format="turtle")

    print("\n=============================")
    print("FINAL MERGED ONTOLOGY")
    print("=============================\n")

    print("Total triples:", len(graph))
    print("Saved to:", OUTPUT_ONTOLOGY)


if __name__ == "__main__":
    main()
