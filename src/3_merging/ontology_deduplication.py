import json
import rdflib
from rdflib import Graph, Namespace, RDF, RDFS, OWL
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from mistralai import Mistral

############################################
# CONFIG
############################################

INPUT_TTL = "ontology_3.ttl"
OUTPUT_TTL = "ontology_dd_4.ttl"

EX = Namespace("https://vocab.cfaa.eus/broaching/")

SIM_THRESHOLD = 0.90

API_KEY = "MISTRAL_API_KEY"
MODEL = "mistral-small-latest"

model = SentenceTransformer("all-MiniLM-L6-v2")
client = Mistral(api_key=API_KEY)

############################################
# LOAD GRAPH
############################################

g = Graph()
g.parse(INPUT_TTL, format="turtle")
g.bind("ex", EX)

print("\nLoaded triples:", len(g))

############################################
# DETECT ENTITY TYPES
############################################

classes = set()
obj_props = set()
data_props = set()
individuals = set()

for s, p, o in g:

    if (s, RDF.type, OWL.Class) in g:
        classes.add(s)

    elif (s, RDF.type, OWL.ObjectProperty) in g:
        obj_props.add(s)

    elif (s, RDF.type, OWL.DatatypeProperty) in g:
        data_props.add(s)

for s in g.subjects(RDF.type, None):

    if (s, RDF.type, OWL.Class) not in g \
       and (s, RDF.type, OWL.ObjectProperty) not in g \
       and (s, RDF.type, OWL.DatatypeProperty) not in g:

        individuals.add(s)

print("\nEntities detected:")
print("Classes:", len(classes))
print("ObjectProperties:", len(obj_props))
print("DatatypeProperties:", len(data_props))
print("Individuals:", len(individuals))

############################################
# GET LABEL
############################################

def get_label(uri):

    for _, _, label in g.triples((uri, RDFS.label, None)):
        return str(label)

    return str(uri).split("/")[-1]

############################################
# SEMANTIC MERGE
############################################

def semantic_merge(entities):

    entities = list(entities)

    if len(entities) < 2:
        return {}

    labels = [get_label(e) for e in entities]

    embeddings = model.encode(labels)

    sim_matrix = cosine_similarity(embeddings)

    mapping = {}

    for i in range(len(entities)):

        for j in range(i + 1, len(entities)):

            score = sim_matrix[i][j]

            if score > SIM_THRESHOLD:

                e1 = entities[i]
                e2 = entities[j]

                rep = min([e1, e2], key=lambda x: len(str(x)))

                if e1 != rep:
                    mapping[e1] = rep

                if e2 != rep:
                    mapping[e2] = rep

                print(
                    f"{str(e1).split('/')[-1]} , {str(e2).split('/')[-1]} → {str(rep).split('/')[-1]}   sim={score:.3f}"
                )

    return mapping

############################################
# RESOLVE TRANSITIVE MERGE
############################################

def resolve_transitive(mapping):

    resolved = {}

    for k in mapping:

        visited = set()
        current = k

        while current in mapping:

            if current in visited:
                break

            visited.add(current)
            current = mapping[current]

        resolved[k] = current

    return resolved

############################################
# BUILD GLOBAL MAPPING
############################################

mapping = {}

print("\n==== MERGING CLASSES ====")
mapping.update(semantic_merge(classes))

print("\n==== MERGING OBJECT PROPERTIES ====")
mapping.update(semantic_merge(obj_props))

print("\n==== MERGING DATATYPE PROPERTIES ====")
mapping.update(semantic_merge(data_props))

print("\n==== MERGING INDIVIDUALS ====")
mapping.update(semantic_merge(individuals))

mapping = resolve_transitive(mapping)

print("\nTotal merged entities:", len(mapping))

############################################
# APPLY MERGE
############################################

merged_graph = Graph()
merged_graph.bind("ex", EX)

for s, p, o in g:

    s_new = mapping.get(s, s)
    p_new = mapping.get(p, p)
    o_new = mapping.get(o, o)

    merged_graph.add((s_new, p_new, o_new))

print("\nTriples after semantic merge:", len(merged_graph))

############################################
# ONTOLOGY CONSISTENCY CHECK PROMPT
############################################

CONSISTENCY_PROMPT = """
You are an ontology validation expert.

Analyse the ontology below and detect structural problems.

Check for:
- redundant classes
- redundant properties
- incorrect domains
- incorrect ranges
- instances without classes
- relations that clearly contradict the ontology

Return ONLY JSON:

{
  "merge_classes":[{"source":"","target":""}],
  "merge_properties":[{"source":"","target":""}],
  "remove_triples":[{"subject":"","predicate":"","object":""}]
}

Use ONLY entities that appear in the ontology.
Return ONLY JSON.

Ontology:
"""

############################################
# LLM CONSISTENCY CHECK
############################################

def ontology_consistency_check(graph):

    ttl = graph.serialize(format="turtle")

    prompt = CONSISTENCY_PROMPT + ttl

    response = client.chat.complete(
        model=MODEL,
        messages=[{"role":"user","content":prompt}]
    )

    text = response.choices[0].message.content

    text = text.replace("```json","").replace("```","")

    try:
        return json.loads(text)
    except:
        print("Invalid JSON from LLM")
        print(text)
        return None

############################################
# APPLY FIXES
############################################

def apply_fixes(graph, fixes):

    if not fixes:
        return graph

    # merge classes
    for m in fixes.get("merge_classes",[]):

        src = EX[m["source"]]
        tgt = EX[m["target"]]

        for s,p,o in list(graph):

            if s == src:
                graph.add((tgt,p,o))
                graph.remove((s,p,o))

            if o == src:
                graph.add((s,p,tgt))
                graph.remove((s,p,o))

    # remove triples
    for t in fixes.get("remove_triples",[]):

        s = EX[t["subject"]]
        p = EX[t["predicate"]]
        o = EX[t["object"]]

        graph.remove((s,p,o))

    return graph

############################################
# RUN CONSISTENCY CHECK
############################################

print("\nRunning ontology consistency check...")

fixes = ontology_consistency_check(merged_graph)

merged_graph = apply_fixes(merged_graph, fixes)

############################################
# SAVE FINAL ONTOLOGY
############################################

merged_graph.serialize(OUTPUT_TTL, format="turtle")

print("\nFinal triples:", len(merged_graph))
print("Saved ontology:", OUTPUT_TTL)
