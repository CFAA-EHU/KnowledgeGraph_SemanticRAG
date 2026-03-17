import sys
from pathlib import Path
from rdflib import Graph
import logging

logger = logging.getLogger(__name__)

TBOX_PATH = Path("data/processed/ontology_aligned.ttl")
ABOX_PATH = Path("data/processed/abox_merged.ttl")

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
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?clase (COUNT(?instancia) AS ?total)
    WHERE {
        ?instancia rdf:type ?clase .
        FILTER(isIRI(?clase))
    }
    GROUP BY ?clase
    ORDER BY DESC(?total)
    LIMIT 10
    """
    
    print("-" * 40)
    print("TOP 10 CLASES CON MÁS INSTANCIAS")
    print("-" * 40)
    
    try:
        resultados = motor.ejecutar_sparql(query_prueba)
        for fila in resultados:
            clase_uri = str(fila.clase)
            clase = clase_uri.split("#")[-1] if "#" in clase_uri else clase_uri.split("/")[-1]
            total = int(fila.total)
            print(f"{clase:<35} | {total}")
    except Exception as e:
        print(f"Error en ejecución SPARQL: {e}")