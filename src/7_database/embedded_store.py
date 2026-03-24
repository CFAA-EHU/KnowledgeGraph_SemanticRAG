import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import argparse
import logging
import sys

from artifact_contracts import OPERATIONAL_ABOX_PATH, OPERATIONAL_TBOX_PATH
from graph_store import GraphDBGraphStore, RDFLibGraphStore, build_graph_store

logger = logging.getLogger(__name__)

TBOX_PATH = OPERATIONAL_TBOX_PATH
ABOX_PATH = OPERATIONAL_ABOX_PATH


class MotorGrafoEmbebido:
    def __init__(self, backend: str = "rdflib"):
        self.store = build_graph_store(backend)
        self.backend = self.store.backend_name()
        if self.backend == "rdflib":
            grafo = self.store.raw_graph()
            logger.info("Motor RDFLib inicializado. Tripletas combinadas en memoria: %s", len(grafo) if grafo is not None else 0)
        else:
            logger.info("Motor GraphDB inicializado contra backend remoto.")

    def ejecutar_sparql(self, query: str):
        if isinstance(self.store, GraphDBGraphStore):
            return self.store.query(query)
        if isinstance(self.store, RDFLibGraphStore):
            return self.store.raw_graph().query(query)
        return self.store.select(query)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecutor manual de SPARQL sobre el runtime operativo.")
    parser.add_argument("--backend", choices=["rdflib", "graphdb"], default="rdflib", help="Backend RDF a usar.")
    parser.add_argument("--query-file", type=Path, default=None, help="Archivo con la consulta SPARQL a ejecutar.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    motor = MotorGrafoEmbebido(backend=args.backend)

    query_prueba = """
    SELECT DISTINCT ?p ?o WHERE {
        VALUES ?s { <https://vocab.cfaa.eus/broaching/MaquinaBrochadoExterior_18> }
        ?s ?p ?o .
        FILTER(CONTAINS(LCASE(STR(?o)), "directiva") || CONTAINS(LCASE(STR(?p)), "normativa"))
    }
    ORDER BY ?p ?o
    """
    if args.query_file is not None:
        query_prueba = args.query_file.read_text(encoding="utf-8")

    print("-" * 80)
    print(f"DIRECTIVAS ASOCIADAS A LA MAQUINA EN EL GRAFO OPERATIVO [{args.backend}]")
    print("-" * 80)

    try:
        resultados = list(motor.ejecutar_sparql(query_prueba))

        if not resultados:
            print("No se obtuvieron resultados para la consulta.")
            sys.exit(0)

        for fila in resultados:
            print([str(valor) for valor in fila])

    except Exception as e:
        print(f"Error en ejecucion SPARQL: {e}")
