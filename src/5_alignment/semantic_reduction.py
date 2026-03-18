import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import re
import sys

from rdflib import Graph, URIRef
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering

from artifact_contracts import EXPERIMENTAL_ABOX_ALIGNED_PATH, OPERATIONAL_ABOX_PATH

GRAPH_PATH = OPERATIONAL_ABOX_PATH
OUTPUT_PATH = EXPERIMENTAL_ABOX_ALIGNED_PATH
SIMILARITY_THRESHOLD = 0.15
BASE_URI = "https://vocab.cfaa.eus/broaching/"

def obtener_entidades_y_etiquetas(g: Graph, clase_objetivo: str) -> tuple[list, list]:
    query = f"""
    PREFIX ex: <{BASE_URI}>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?e ?texto WHERE {{
        ?e a {clase_objetivo} .
        OPTIONAL {{ ?e ex:textoExtracto ?texto . }}
        OPTIONAL {{ ?e rdfs:label ?texto . }}
        FILTER(isIRI(?e))
    }}
    """

    entidades_dict = {}
    for row in g.query(query):
        uri = str(row.e)
        if row.texto:
            entidades_dict[uri] = str(row.texto)
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
        linkage="average",
    )
    clusters = clustering.fit_predict(embeddings)

    grupos = {}
    for idx, cluster_id in enumerate(clusters):
        grupos.setdefault(cluster_id, []).append(uris[idx])

    mapeo = {}
    for _, lista_uris in grupos.items():
        if len(lista_uris) > 1:
            canonica = sorted(lista_uris, key=len)[0]
            for uri in lista_uris:
                if uri != canonica:
                    mapeo[URIRef(uri)] = URIRef(canonica)

    return mapeo

def alinear_instancias():
    if not GRAPH_PATH.exists():
        print(f"Error: {GRAPH_PATH} no existe. Ejecuta primero abox_merger.py")
        sys.exit(1)

    g = Graph()
    g.parse(GRAPH_PATH, format="turtle")

    clases_hardware = ["ex:Componente", "ex:PiezaRecambio", "ex:Sistema", "ex:Consumible"]

    uris_totales = []
    labels_totales = []

    for clase in clases_hardware:
        uris, labels = obtener_entidades_y_etiquetas(g, clase)
        uris_totales.extend(uris)
        labels_totales.extend(labels)

    print("Cargando modelo all-MiniLM-L6-v2...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    mapeo_global = {}

    if uris_totales:
        print(f"Clusterizando {len(uris_totales)} instancias de hardware...")
        mapeo_global.update(clusterizar_entidades(uris_totales, labels_totales, model))
    else:
        print("No se encontraron instancias de hardware para clusterizar.")

    print(f"Detectadas {len(mapeo_global)} URIs redundantes. Reescribiendo grafo A-Box...")

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

    print("-" * 40)
    print("RESUMEN DE ALINEAMIENTO DE ENTIDADES (A-BOX)")
    print("-" * 40)
    print(f"Tripletas mutadas       : {reemplazos}")
    print(f"Nodos fusionados        : {len(mapeo_global)}")
    print(f"Archivo generado        : {OUTPUT_PATH}")

if __name__ == "__main__":
    alinear_instancias()
