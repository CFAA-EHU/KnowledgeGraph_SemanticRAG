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
            print("Error: Faltan archivos T-Box o A-Box en el directorio.")
            sys.exit(1)

        logger.info("Ingestando T-Box (Esquema)...")
        self.grafo.parse(TBOX_PATH, format="turtle")

        logger.info("Ingestando A-Box (Instancias)...")
        self.grafo.parse(ABOX_PATH, format="turtle")

        logger.info(f"Motor inicializado. Tripletas combinadas en memoria: {len(self.grafo)}")

    def ejecutar_sparql(self, query: str):
        return self.grafo.query(query)

if __name__ == "__main__":
    motor = MotorGrafoEmbebido()

    query_prueba = """
    SELECT DISTINCT ?s ?p ?o WHERE {
        {
            VALUES ?s { <https://vocab.cfaa.eus/broaching/DirectivaSeguridadUnionEuropea_18> }
            ?s ?p ?o .
            FILTER(?o = <https://vocab.cfaa.eus/broaching/Directiva2006_42_CE>)
        }
        UNION
        {
            VALUES ?s { <https://vocab.cfaa.eus/broaching/Directiva2006_42_CE> }
            ?s ?p ?o .
            FILTER(?o = <https://vocab.cfaa.eus/broaching/DirectivaSeguridadUnionEuropea_18>)
        }
    }
    ORDER BY ?s ?p ?o
    """

    print("-" * 80)
    print("NORMATIVAS QUE CUMPLE LA MAQUINA")
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