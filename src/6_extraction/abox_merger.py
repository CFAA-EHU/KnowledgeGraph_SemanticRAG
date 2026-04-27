import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS

from artifact_contracts import ABOX_CHUNKS_DIR, ABOX_MINTED_ENTITY_REGISTRY_PATH, OPERATIONAL_TBOX_PATH, RAW_MERGED_ABOX_PATH
from abox_graph_sanitizer import SanitizationResult, load_mint_registry, sanitize_abox_graph, save_mint_registry


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


def _build_subclass_closure(tbox_graph: Graph) -> dict[str, set[str]]:
    parents: dict[str, set[str]] = {}
    for child, _, parent in tbox_graph.triples((None, RDFS.subClassOf, None)):
        if isinstance(child, URIRef) and isinstance(parent, URIRef):
            parents.setdefault(str(child), set()).add(str(parent))

    closure: dict[str, set[str]] = {}

    def visit(uri: str, seen: set[str] | None = None) -> set[str]:
        if uri in closure:
            return closure[uri]
        seen = seen or set()
        if uri in seen:
            return set()
        seen.add(uri)
        ancestors = set(parents.get(uri, set()))
        for parent_uri in list(ancestors):
            ancestors |= visit(parent_uri, seen)
        closure[uri] = ancestors
        return ancestors

    for uri in parents:
        visit(uri)
    return closure


def validate_merged_uri_consistency(graph: Graph, *, tbox_graph: Graph, output_path: Path) -> None:
    subclass_closure = _build_subclass_closure(tbox_graph)
    issues: list[dict[str, object]] = []
    blockers: list[dict[str, object]] = []
    report_path = output_path.with_name(f"{output_path.stem}_uri_collision_report.json")

    for subject in {subject for subject in graph.subjects() if isinstance(subject, URIRef)}:
        types = sorted({str(obj) for obj in graph.objects(subject, RDF.type) if isinstance(obj, URIRef)})
        labels = sorted({str(obj) for obj in graph.objects(subject, RDFS.label)})
        identifiers = sorted({str(obj) for obj in graph.objects(subject, URIRef("https://vocab.cfaa.eus/broaching/identificador"))})

        incomparable_types = []
        for type_uri in types:
            incompatible = [
                other
                for other in types
                if other != type_uri
                and other not in subclass_closure.get(type_uri, set())
                and type_uri not in subclass_closure.get(other, set())
            ]
            if incompatible:
                incomparable_types = sorted(set([type_uri, *incompatible]))
                break

        divergent_surfaces = len(labels) > 1 and len({label.lower() for label in labels}) > 1
        divergent_identifiers = len(identifiers) > 1 and len({identifier.lower() for identifier in identifiers}) > 1

        if incomparable_types or divergent_surfaces or divergent_identifiers:
            issue = {
                "subject": str(subject),
                "types": types,
                "labels": labels[:5],
                "identifiers": identifiers[:5],
                "incomparable_types": incomparable_types,
                "divergent_surfaces": divergent_surfaces,
                "divergent_identifiers": divergent_identifiers,
            }
            issues.append(issue)

            # Canonicalization is the stage that decides whether these divergences
            # collapse into one entity or stay separated. At merge time we record
            # the strongest candidates but do not block the upstream artifact.
            if incomparable_types and divergent_identifiers:
                blockers.append(issue)

    if issues:
        report_path.write_text(
            json.dumps(
                {
                    "issue_count": len(issues),
                    "blocker_count": len(blockers),
                    "issues": issues[:100],
                    "blockers": blockers[:100],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Aviso: se detectaron colisiones de URI candidatas a resolución canónica. Ver {report_path}")
    elif report_path.exists():
        report_path.unlink()


def merge_from_directory(
    input_dir: Path,
    *,
    tbox_graph: Graph,
    mint_registry: dict[str, str],
) -> tuple[Graph, int, int, SanitizationResult]:
    if not input_dir.exists():
        raise SystemExit(f"Error: Directorio no encontrado - {input_dir}")

    archivos_ttl = sorted(input_dir.glob("*_abox.ttl"))
    if not archivos_ttl:
        raise SystemExit("Error: No hay archivos TTL A-Box para procesar.")

    grafo_unificado = Graph()
    exitos = 0
    errores = 0
    aggregate_result = SanitizationResult()

    print(f"Iniciando consolidacion de {len(archivos_ttl)} fragmentos A-Box desde {input_dir}...")
    for archivo in archivos_ttl:
        try:
            chunk_graph = load_ttl_graph(archivo)
            chunk_graph, chunk_result = sanitize_abox_graph(
                chunk_graph,
                tbox_graph=tbox_graph,
                mint_registry=mint_registry,
            )
            aggregate_result.minted_nodes += chunk_result.minted_nodes
            aggregate_result.reused_registry_iris += chunk_result.reused_registry_iris
            aggregate_result.replaced_file_iris += chunk_result.replaced_file_iris
            aggregate_result.purged_file_iris += chunk_result.purged_file_iris
            aggregate_result.redundant_type_triples_removed += chunk_result.redundant_type_triples_removed
            aggregate_result.invalid_hex_binary_literals_downgraded += chunk_result.invalid_hex_binary_literals_downgraded
            aggregate_result.texto_extracto_removed += chunk_result.texto_extracto_removed
            aggregate_result.texto_extracto_trimmed += chunk_result.texto_extracto_trimmed
            aggregate_result.minted_assignments.update(chunk_result.minted_assignments)
            grafo_unificado += chunk_graph
            exitos += 1
        except Exception as exc:
            print(f"Corrupcion detectada en {archivo.name}: descartado. Detalles: {exc}")
            errores += 1
    return grafo_unificado, exitos, errores, aggregate_result


def merge_from_graphs(
    paths: list[Path],
    *,
    tbox_graph: Graph,
    mint_registry: dict[str, str],
) -> tuple[Graph, int, SanitizationResult]:
    grafo_unificado = Graph()
    exitos = 0
    aggregate_result = SanitizationResult()
    for path in paths:
        if not path.exists():
            raise SystemExit(f"Error: Grafo A-Box requerido no encontrado - {path}")
        chunk_graph = load_ttl_graph(path)
        chunk_graph, chunk_result = sanitize_abox_graph(
            chunk_graph,
            tbox_graph=tbox_graph,
            mint_registry=mint_registry,
        )
        aggregate_result.minted_nodes += chunk_result.minted_nodes
        aggregate_result.reused_registry_iris += chunk_result.reused_registry_iris
        aggregate_result.replaced_file_iris += chunk_result.replaced_file_iris
        aggregate_result.purged_file_iris += chunk_result.purged_file_iris
        aggregate_result.redundant_type_triples_removed += chunk_result.redundant_type_triples_removed
        aggregate_result.invalid_hex_binary_literals_downgraded += chunk_result.invalid_hex_binary_literals_downgraded
        aggregate_result.texto_extracto_removed += chunk_result.texto_extracto_removed
        aggregate_result.texto_extracto_trimmed += chunk_result.texto_extracto_trimmed
        aggregate_result.minted_assignments.update(chunk_result.minted_assignments)
        grafo_unificado += chunk_graph
        exitos += 1
    return grafo_unificado, exitos, aggregate_result


def main() -> None:
    args = parse_args()
    input_graphs = list(args.input_graphs or [])

    if args.input_dir is None and not input_graphs:
        args.input_dir = ABOX_CHUNKS_DIR

    grafo_unificado = Graph()
    exitos = 0
    errores = 0
    fuentes = []

    tbox_graph = load_ttl_graph(OPERATIONAL_TBOX_PATH)
    mint_registry = load_mint_registry(ABOX_MINTED_ENTITY_REGISTRY_PATH)
    directory_sanitization = SanitizationResult()
    input_graph_sanitization = SanitizationResult()

    if args.input_dir is not None:
        grafo_directorio, exitos, errores, directory_sanitization = merge_from_directory(
            args.input_dir,
            tbox_graph=tbox_graph,
            mint_registry=mint_registry,
        )
        grafo_unificado += grafo_directorio
        fuentes.append(str(args.input_dir))

    if input_graphs:
        grafo_extra, exitos_extra, input_graph_sanitization = merge_from_graphs(
            input_graphs,
            tbox_graph=tbox_graph,
            mint_registry=mint_registry,
        )
        grafo_unificado += grafo_extra
        exitos += exitos_extra
        fuentes.extend(str(path) for path in input_graphs)

    grafo_unificado, _ = sanitize_abox_graph(
        grafo_unificado,
        tbox_graph=tbox_graph,
        mint_registry=mint_registry,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    grafo_unificado.serialize(destination=args.output, format="turtle")
    save_mint_registry(mint_registry, ABOX_MINTED_ENTITY_REGISTRY_PATH)

    serialized_graph = load_ttl_graph(args.output)
    validate_merged_uri_consistency(serialized_graph, tbox_graph=tbox_graph, output_path=args.output)

    print("-" * 40)
    print("RESUMEN DE CONSOLIDACION A-BOX")
    print("-" * 40)
    print(f"Fuentes fusionadas   : {fuentes}")
    print(f"Entradas procesadas  : {exitos}")
    print(f"Entradas corruptas   : {errores}")
    print(f"IRIs saneadas por chunk: {directory_sanitization.minted_nodes}")
    print(f"IRIs saneadas por grafo fusionado: {input_graph_sanitization.minted_nodes}")
    print(f"Tripletas totales    : {len(grafo_unificado)}")
    print(f"Archivo generado     : {args.output}")


if __name__ == "__main__":
    main()
