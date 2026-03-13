import re
import rdflib
from rdflib import Graph, RDF, RDFS, OWL
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from mistralai import Mistral

############################################
# CONFIG
############################################

ONTOLOGY_FILE = "ontology_dd_4.ttl"
SPARQL_FILE = "consultas_sparql.txt"

API_KEY = "HMXKoCPyStwJ9DjLnGQbKYMg2KqCiEUs"
MODEL = "mistral-small-latest"

COSINE_THRESHOLD = 0.85

client = Mistral(api_key=API_KEY)

embedder = SentenceTransformer("all-MiniLM-L6-v2")

############################################
# LOAD SPARQL QUERIES
############################################

def load_sparql():

    with open(SPARQL_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    queries = re.findall(r"<SPARQL>(.*?)</SPARQL>", text, re.DOTALL)

    return [q.strip() for q in queries]

############################################
# LOAD ONTOLOGY
############################################

g = Graph()
g.parse(ONTOLOGY_FILE, format="turtle")

print("Loaded ontology triples:", len(g))

############################################
# EXTRACT SCHEMA (T-BOX)
############################################

classes = set()
obj_props = set()
data_props = set()

for s, p, o in g:

    if (s, RDF.type, OWL.Class) in g:
        classes.add(str(s))

    if (s, RDF.type, OWL.ObjectProperty) in g:
        obj_props.add(str(s))

    if (s, RDF.type, OWL.DatatypeProperty) in g:
        data_props.add(str(s))

schema_entities = classes.union(obj_props).union(data_props)

print("Classes:", len(classes))
print("ObjectProperties:", len(obj_props))
print("DatatypeProperties:", len(data_props))

############################################
# EXTRACT ENTITIES FROM SPARQL
############################################

def extract_sparql_entities(query):

    # remove PREFIX lines
    query = re.sub(r'PREFIX\s+\w+:\s*<[^>]+>', '', query, flags=re.IGNORECASE)

    entities = re.findall(r'\b[a-zA-Z_]+:[a-zA-Z0-9_]+\b', query)

    return list(set(entities))

############################################
# 5.2 T-BOX VALIDATION
############################################

def validate_tbox(query):

    entities = extract_sparql_entities(query)

    invalid = []

    for e in entities:

        uri = e.split(":")[1]

        found = False

        for s in schema_entities:
            if s.endswith(uri):
                found = True
                break

        if not found:
            invalid.append(e)

    if invalid:

        print("❌ T-Box validation failed")
        print("Invalid identifiers:", invalid)
        return False

    print("✅ T-Box validation passed")

    return True

############################################
# 5.3 DOMAIN RANGE VALIDATION
############################################

def get_domain_range(prop):

    domain = None
    range_ = None

    for s, p, o in g.triples((prop, RDFS.domain, None)):
        domain = o

    for s, p, o in g.triples((prop, RDFS.range, None)):
        range_ = o

    return domain, range_


def extract_triples(query):

    pattern = r'(\?\w+|\w+:\w+)\s+(\w+:\w+)\s+(\?\w+|\w+:\w+|\".*?\")'

    triples = re.findall(pattern, query)

    return triples


def validate_domain_range(query):

    triples = extract_triples(query)

    for subj, pred, obj in triples:

        prop_uri = None

        for s in obj_props.union(data_props):
            if s.endswith(pred.split(":")[1]):
                prop_uri = rdflib.URIRef(s)
                break

        if not prop_uri:
            continue

        domain, range_ = get_domain_range(prop_uri)

        print("\nChecking property:", pred)
        print("Domain:", domain)
        print("Range:", range_)

    print("✅ Domain/Range validation completed")

    return True

############################################
# BACK TRANSLATION (SPARQL → NL)
############################################

def sparql_to_text(query):

    prompt = f"""
You are an expert in SPARQL interpretation.

Explain in one short sentence what the following SPARQL query retrieves.

Return only the explanation.

SPARQL query:
{query}
"""

    response = client.chat.complete(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content.strip()

############################################
# 5.4 COSINE SIMILARITY VALIDATION
############################################

def cosine_validation(original_question, back_translation):

    embeddings = embedder.encode([original_question, back_translation])

    sim = cosine_similarity(
        [embeddings[0]],
        [embeddings[1]]
    )[0][0]

    print("\nOriginal question:", original_question)
    print("Back translation:", back_translation)

    print("\nCosine similarity:", sim)

    if sim >= COSINE_THRESHOLD:
        print("✅ Semantic alignment passed")
        return True

    else:
        print("❌ Semantic alignment failed")
        return False

############################################
# COMPLETE VALIDATION PIPELINE
############################################

def validate_query(question, sparql):

    print("\n===============================")
    print("SPARQL VALIDATION PIPELINE")
    print("===============================\n")

    print("SPARQL query:\n")
    print(sparql)

    if not validate_tbox(sparql):
        return False

    validate_domain_range(sparql)

    back_translation = sparql_to_text(sparql)

    if not cosine_validation(question, back_translation):
        return False

    print("\n✅ Query accepted")

    return True

############################################
# RUN VALIDATION FOR ALL QUERIES
############################################

if __name__ == "__main__":

    queries = load_sparql()

    print("\nLoaded SPARQL queries:", len(queries))

    for i, q in enumerate(queries):

        question = f"Question {i+1}"

        validate_query(question, q)

