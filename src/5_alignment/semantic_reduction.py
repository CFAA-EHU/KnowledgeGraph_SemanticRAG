import sys
import re
from pathlib import Path
from rdflib import Graph, URIRef
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering

GRAPH_PATH = Path("data/processed/ontology_merged.ttl")
OUTPUT_PATH = Path("data/processed/ontology_aligned.ttl")
SIMILARITY_THRESHOLD = 0.15

def obtener_entidades_y_etiquetas(g: Graph, tipo_entidad: str) -> tuple[list, list]:
    query = f"""
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?e ?label WHERE {{
        ?e a {tipo_entidad} .
        OPTIONAL {{ ?e rdfs:label ?label . }}
        FILTER(isIRI(?e))
    }}
    """
    
    entidades_dict = {}
    for row in g.query(query):
        uri = str(row.e)
        if row.label:
            entidades_dict[uri] = str(row.label)
        elif uri not in entidades_dict:
            base = uri.split("#")[-1] if "#" in uri else uri.split("/")[-1]
            entidades_dict[uri] = re.sub(r"([a-z])([A-Z])", r"\1 \2", base)
            
    return list(entidades_dict.keys()), list(entidades_dict.values())

def clusterizar_entidades(uris: list, labels: list, model: SentenceTransformer) -> dict:
    if len(uris) < 2:
        return {}

    embeddings = model.encode(labels)
    
    clustering = AgglomerativeClustering(
        n_clusters=None, 
        distance_threshold=SIMILARITY_THRESHOLD, 
        metric="cosine", 
        linkage="average"
    )
    clusters = clustering.fit_predict(embeddings)

    grupos = {}
    for idx, cluster_id in enumerate(clusters):
        grupos.setdefault(cluster_id, []).append(uris[idx])

    mapeo = {}
    for cluster_id, lista_uris in grupos.items():
        if len(lista_uris) > 1:
            canonica = sorted(lista_uris, key=len)[0]
            for uri in lista_uris:
                if uri != canonica:
                    mapeo[URIRef(uri)] = URIRef(canonica)

    return mapeo

def alinear_ontologia():
    if not GRAPH_PATH.exists():
        print(f"Error: {GRAPH_PATH} no existe.")
        sys.exit(1)

    g = Graph()
    g.parse(GRAPH_PATH, format="turtle")

    uris_clases, labels_clases = obtener_entidades_y_etiquetas(g, "owl:Class")
    uris_rdfs, labels_rdfs = obtener_entidades_y_etiquetas(g, "rdfs:Class")
    
    uris_clases_total = list(set(uris_clases + uris_rdfs))
    labels_clases_total = [labels_clases[uris_clases.index(u)] if u in uris_clases else labels_rdfs[uris_rdfs.index(u)] for u in uris_clases_total]

    uris_op, labels_op = obtener_entidades_y_etiquetas(g, "owl:ObjectProperty")
    uris_dp, labels_dp = obtener_entidades_y_etiquetas(g, "owl:DatatypeProperty")

    print("Cargando modelo all-MiniLM-L6-v2...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    mapeo_global = {}

    print(f"Clusterizando {len(uris_clases_total)} Clases...")
    mapeo_global.update(clusterizar_entidades(uris_clases_total, labels_clases_total, model))

    print(f"Clusterizando {len(uris_op)} Object Properties...")
    mapeo_global.update(clusterizar_entidades(uris_op, labels_op, model))

    print(f"Clusterizando {len(uris_dp)} Datatype Properties...")
    mapeo_global.update(clusterizar_entidades(uris_dp, labels_dp, model))

    print(f"Detectadas {len(mapeo_global)} URIs redundantes. Reescribiendo grafo...")

    g_nuevo = Graph()
    for ns_prefix, ns_uri in g.namespaces():
        g_nuevo.bind(ns_prefix, ns_uri)

    reemplazos = 0
    for s, p, o in g:
        new_s = mapeo_global.get(s, s)
        new_p = mapeo_global.get(p, p)
        new_o = mapeo_global.get(o, o)
        if new_s != s or new_p != p or new_o != o:
            reemplazos += 1
        g_nuevo.add((new_s, new_p, new_o))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    g_nuevo.serialize(destination=OUTPUT_PATH, format="turtle")

    def count_remaining(uris):
        return len(uris) - sum(1 for k in mapeo_global if str(k) in uris)

    print("-" * 40)
    print("RESUMEN DE REDUCCIÓN SEMÁNTICA SEGREGADA")
    print("-" * 40)
    print(f"Tripletas mutadas       : {reemplazos}")
    print(f"Clases consolidadas     : {count_remaining(uris_clases_total)}")
    print(f"Obj Props consolidadas  : {count_remaining(uris_op)}")
    print(f"Data Props consolidadas : {count_remaining(uris_dp)}")
    print(f"Archivo generado        : {OUTPUT_PATH}")

if __name__ == "__main__":
    alinear_ontologia()