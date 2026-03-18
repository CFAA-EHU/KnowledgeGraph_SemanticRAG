import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import sys

from rdflib import Graph

from artifact_contracts import ABOX_CHUNKS_DIR, OPERATIONAL_ABOX_PATH

INPUT_DIR = ABOX_CHUNKS_DIR
OUTPUT_FILE = OPERATIONAL_ABOX_PATH

def unificar_abox():
    if not INPUT_DIR.exists():
        print(f"Error: Directorio no encontrado - {INPUT_DIR}")
        sys.exit(1)

    archivos_ttl = list(INPUT_DIR.glob("*_abox.ttl"))
    if not archivos_ttl:
        print("Error: No hay archivos TTL A-Box para procesar.")
        sys.exit(1)

    grafo_unificado = Graph()
    exitos = 0
    errores = 0

    print(f"Iniciando consolidacion de {len(archivos_ttl)} fragmentos A-Box...")

    for archivo in archivos_ttl:
        try:
            grafo_temporal = Graph()
            grafo_temporal.parse(archivo, format="turtle")
            grafo_unificado += grafo_temporal
            exitos += 1
        except Exception as e:
            print(f"Corrupcion detectada en {archivo.name}: descartado. Detalles: {e}")
            errores += 1

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    grafo_unificado.serialize(destination=OUTPUT_FILE, format="turtle")

    print("-" * 40)
    print("RESUMEN DE CONSOLIDACION A-BOX")
    print("-" * 40)
    print(f"Fragmentos fusionados : {exitos}")
    print(f"Fragmentos corruptos  : {errores}")
    print(f"Tripletas totales     : {len(grafo_unificado)}")
    print(f"Archivo generado      : {OUTPUT_FILE}")

if __name__ == "__main__":
    unificar_abox()
