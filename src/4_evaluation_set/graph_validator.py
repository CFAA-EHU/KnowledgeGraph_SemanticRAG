import sys
from pathlib import Path
from rdflib import Graph

GRAPH_PATH = Path("data/processed/ontology_merged.ttl")

def auditar_grafo():
    if not GRAPH_PATH.exists():
        print(f"Error: {GRAPH_PATH} no encontrado.")
        sys.exit(1)

    g = Graph()
    print("Cargando grafo consolidado en memoria para auditoría SPARQL...")
    g.parse(GRAPH_PATH, format="turtle")

    q_classes = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT (COUNT(DISTINCT ?c) AS ?count)
    WHERE {
        { ?c a owl:Class . } UNION { ?c a rdfs:Class . }
    }
    """

    q_obj_props = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT (COUNT(DISTINCT ?p) AS ?count)
    WHERE { ?p a owl:ObjectProperty . }
    """

    q_data_props = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT (COUNT(DISTINCT ?p) AS ?count)
    WHERE { ?p a owl:DatatypeProperty . }
    """

    num_clases = list(g.query(q_classes))[0][0]
    num_obj_props = list(g.query(q_obj_props))[0][0]
    num_data_props = list(g.query(q_data_props))[0][0]

    print("-" * 40)
    print("MÉTRICAS T-BOX (CONSOLIDADO)")
    print("-" * 40)
    print(f"Clases únicas          : {num_clases}")
    print(f"Object Properties      : {num_obj_props}")
    print(f"Datatype Properties    : {num_data_props}")

if __name__ == "__main__":
    auditar_grafo()