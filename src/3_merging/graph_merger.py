import sys
from pathlib import Path
from rdflib import Graph

INPUT_DIR = Path("data/processed/graphs/")
OUTPUT_FILE = Path("data/processed/ontology_merged.ttl")

def unificar_grafos():
    if not INPUT_DIR.exists():
        print(f"Error: Directorio no encontrado - {INPUT_DIR}")
        sys.exit(1)

    archivos_ttl = list(INPUT_DIR.glob("*.ttl"))
    if not archivos_ttl:
        print("Error: No hay archivos TTL para procesar.")
        sys.exit(1)

    grafo_unificado = Graph()
    exitos = 0
    errores = 0

    print(f"Iniciando consolidación de {len(archivos_ttl)} fragmentos...")

    for archivo in archivos_ttl:
        try:
            grafo_temporal = Graph()
            grafo_temporal.parse(archivo, format="turtle")
            grafo_unificado += grafo_temporal
            exitos += 1
        except Exception as e:
            print(f"Corrupción detectada en {archivo.name}: descartado. Detalles: {e}")
            errores += 1

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    grafo_unificado.serialize(destination=OUTPUT_FILE, format="turtle")

    print("-" * 40)
    print("RESUMEN DE CONSOLIDACIÓN")
    print("-" * 40)
    print(f"Fragmentos fusionados : {exitos}")
    print(f"Fragmentos corruptos  : {errores}")
    print(f"Tripletas totales     : {len(grafo_unificado)}")
    print(f"Archivo generado      : {OUTPUT_FILE}")

if __name__ == "__main__":
    unificar_grafos()