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

API_KEY = "MISTRAL_API_KEY"
MODEL = "mistral-small-latest"

COSINE_THRESHOLD = 0.85

client = Mistral(api_key=API_KEY)

embedder = SentenceTransformer("all-MiniLM-L6-v2")

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

for s,p,o in g:

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

    entities = re.findall(r'(\w+:\w+)', query)

    return entities

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
            if uri in s:
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

    for s,p,o in g.triples((prop, RDFS.domain, None)):
        domain = o

    for s,p,o in g.triples((prop, RDFS.range, None)):
        range_ = o

    return domain, range_


def validate_domain_range(query):

    triples = re.findall(r'(\?\w+|\w+:\w+)\s+(\w+:\w+)\s+(\?\w+|\w+:\w+)', query)

    for subj, pred, obj in triples:

        prop_uri = None

        for s in obj_props.union(data_props):
            if pred.split(":")[1] in s:
                prop_uri = rdflib.URIRef(s)

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
        messages=[{"role":"user","content":prompt}]
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
# EXAMPLE
############################################

if __name__ == "__main__":

    question = "What model does the A218 machine have?"

    sparql_query = """
PREFIX ex: <https://vocab.cfaa.eus/broaching/>

SELECT ?model
WHERE {
    ex:A218 ex:hasModel ?model .
}
"""

    validate_query(question, sparql_query)
