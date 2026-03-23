import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import logging
import sys

from rdflib import Graph

from artifact_contracts import OPERATIONAL_ABOX_PATH, OPERATIONAL_TBOX_PATH

logger = logging.getLogger(__name__)

TBOX_PATH = OPERATIONAL_TBOX_PATH
ABOX_PATH = OPERATIONAL_ABOX_PATH


class MotorGrafoEmbebido:
    def __init__(self):
        self.grafo = Graph()
        self._cargar_datos()

    def _cargar_datos(self):
        if not TBOX_PATH.exists() or not ABOX_PATH.exists():
            print("Error: Faltan la T-Box canonica o la A-Box operativa linked en el directorio.")
            sys.exit(1)

        logger.info("Ingestando T-Box canonica...")
        self.grafo.parse(TBOX_PATH, format="turtle")

        logger.info("Ingestando A-Box operativa linked...")
        self.grafo.parse(ABOX_PATH, format="turtle")

        logger.info(f"Motor inicializado. Tripletas combinadas en memoria: {len(self.grafo)}")

    def ejecutar_sparql(self, query: str):
        return self.grafo.query(query)


if __name__ == "__main__":
    motor = MotorGrafoEmbebido()

    query_prueba = """
    SELECT DISTINCT ?p ?o WHERE {
        VALUES ?s { <https://vocab.cfaa.eus/broaching/MaquinaBrochadoExterior_18> }
        ?s ?p ?o .
        FILTER(CONTAINS(LCASE(STR(?o)), "directiva") || CONTAINS(LCASE(STR(?p)), "normativa"))
    }
    ORDER BY ?p ?o
    """

    print("-" * 80)
    print("DIRECTIVAS ASOCIADAS A LA MAQUINA EN EL GRAFO ENRIQUECIDO")
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
