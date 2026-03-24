import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse

from rdflib import Graph

from artifact_contracts import ABOX_CHUNKS_DIR, RAW_MERGED_ABOX_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge A-Box TTL fragments or already-merged graphs into a single Turtle output.")
    parser.add_argument("--input-dir", type=Path, default=None, help="Directorio opcional con archivos *_abox.ttl a fusionar.")
    parser.add_argument("--input-graphs", nargs="*", type=Path, default=None, help="Grafo(s) TTL adicionales ya fusionados para unir al resultado.")
    parser.add_argument("--output", type=Path, default=RAW_MERGED_ABOX_PATH, help="Archivo TTL de salida.")
    return parser.parse_args()


def load_ttl_graph(path: Path) -> Graph:
    graph = Graph()
    graph.parse(path, format="turtle")
    return graph


def merge_from_directory(input_dir: Path) -> tuple[Graph, int, int]:
    if not input_dir.exists():
        raise SystemExit(f"Error: Directorio no encontrado - {input_dir}")

    archivos_ttl = sorted(input_dir.glob("*_abox.ttl"))
    if not archivos_ttl:
        raise SystemExit("Error: No hay archivos TTL A-Box para procesar.")

    grafo_unificado = Graph()
    exitos = 0
    errores = 0

    print(f"Iniciando consolidacion de {len(archivos_ttl)} fragmentos A-Box desde {input_dir}...")
    for archivo in archivos_ttl:
        try:
            grafo_unificado += load_ttl_graph(archivo)
            exitos += 1
        except Exception as exc:
            print(f"Corrupcion detectada en {archivo.name}: descartado. Detalles: {exc}")
            errores += 1
    return grafo_unificado, exitos, errores


def merge_from_graphs(paths: list[Path]) -> tuple[Graph, int]:
    grafo_unificado = Graph()
    exitos = 0
    for path in paths:
        if not path.exists():
            raise SystemExit(f"Error: Grafo A-Box requerido no encontrado - {path}")
        grafo_unificado += load_ttl_graph(path)
        exitos += 1
    return grafo_unificado, exitos


def main() -> None:
    args = parse_args()
    input_graphs = list(args.input_graphs or [])

    if args.input_dir is None and not input_graphs:
        args.input_dir = ABOX_CHUNKS_DIR

    grafo_unificado = Graph()
    exitos = 0
    errores = 0
    fuentes = []

    if args.input_dir is not None:
        grafo_directorio, exitos, errores = merge_from_directory(args.input_dir)
        grafo_unificado += grafo_directorio
        fuentes.append(str(args.input_dir))

    if input_graphs:
        grafo_extra, exitos_extra = merge_from_graphs(input_graphs)
        grafo_unificado += grafo_extra
        exitos += exitos_extra
        fuentes.extend(str(path) for path in input_graphs)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    grafo_unificado.serialize(destination=args.output, format="turtle")

    print("-" * 40)
    print("RESUMEN DE CONSOLIDACION A-BOX")
    print("-" * 40)
    print(f"Fuentes fusionadas   : {fuentes}")
    print(f"Entradas procesadas  : {exitos}")
    print(f"Entradas corruptas   : {errores}")
    print(f"Tripletas totales    : {len(grafo_unificado)}")
    print(f"Archivo generado     : {args.output}")


if __name__ == "__main__":
    main()
