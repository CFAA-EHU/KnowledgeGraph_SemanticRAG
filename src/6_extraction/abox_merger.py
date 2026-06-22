import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
import re
from collections import defaultdict

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS

from artifact_contracts import (
    ABOX_CHUNKS_DIR,
    ABOX_MERGER_IDENTIFIER_COLLISIONS_PATH,
    ABOX_MERGER_MARKED_CHUNKS_PATH,
    ABOX_MERGER_REJECTED_CHUNKS_PATH,
    ABOX_MINTED_ENTITY_REGISTRY_PATH,
    OPERATIONAL_TBOX_PATH,
    RAW_MERGED_ABOX_PATH,
)
from abox_graph_sanitizer import (
    SanitizationResult,
    downgrade_invalid_hex_binary_literals,
    drop_incidental_table_types,
    drop_redundant_supertypes,
    ensure_minimal_traceability,
    infer_missing_types,
    load_mint_registry,
    purge_phrase_like_entities,
    prune_or_scope_texto_extracto,
    sanitize_abox_graph,
    save_mint_registry,
)
from abox_semantic_validator import SemanticVocabulary, load_semantic_vocabulary, validate_abox_graph


CHUNK_REJECTION_FAILURES = {
    "non_canonical_class",
    "non_canonical_property",
    "blank_node_entity",
    "file_uri_entity",
    "individual_used_as_class",
}
EX_NS = "https://vocab.cfaa.eus/broaching/"
EX_IDENTIFICADOR = URIRef(EX_NS + "identificador")


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
        print(f"Warning: URI collisions detected as candidates for canonical resolution. See {report_path}")
    elif report_path.exists():
        report_path.unlink()


def normalize_identifier(value: str) -> str:
    return re.sub(r"[\s\-/]+", "", value or "").upper()


def report_identifier_collisions(graph: Graph) -> dict[str, object]:
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for subject in graph.subjects(RDF.type, None):
        if not isinstance(subject, URIRef):
            continue
        types = [
            str(obj).replace(EX_NS, "")
            for obj in graph.objects(subject, RDF.type)
            if isinstance(obj, URIRef) and str(obj).startswith(EX_NS)
        ]
        identifiers = [
            normalize_identifier(str(obj))
            for obj in graph.objects(subject, EX_IDENTIFICADOR)
            if isinstance(obj, Literal) and str(obj).strip()
        ]
        for entity_type in types:
            for identifier in identifiers:
                if len(identifier) >= 2:
                    groups[(entity_type, identifier)].append(str(subject))

    collisions = {
        f"{entity_type}::{identifier}": list(dict.fromkeys(uris))
        for (entity_type, identifier), uris in groups.items()
        if len(set(uris)) > 1
    }
    by_class: dict[str, int] = defaultdict(int)
    for key in collisions:
        by_class[key.split("::", 1)[0]] += 1
    return {
        "total_collision_groups": len(collisions),
        "collisions_by_class": dict(sorted(by_class.items())),
        "sample_collisions": dict(list(sorted(collisions.items()))[:20]),
    }


def _collect_sanitization(aggregate_result: SanitizationResult, chunk_result: SanitizationResult) -> None:
    aggregate_result.minted_nodes += chunk_result.minted_nodes
    aggregate_result.reused_registry_iris += chunk_result.reused_registry_iris
    aggregate_result.replaced_file_iris += chunk_result.replaced_file_iris
    aggregate_result.purged_file_iris += chunk_result.purged_file_iris
    aggregate_result.redundant_type_triples_removed += chunk_result.redundant_type_triples_removed
    aggregate_result.inferred_missing_types += chunk_result.inferred_missing_types
    aggregate_result.invalid_hex_binary_literals_downgraded += chunk_result.invalid_hex_binary_literals_downgraded
    aggregate_result.texto_extracto_removed += chunk_result.texto_extracto_removed
    aggregate_result.texto_extracto_trimmed += chunk_result.texto_extracto_trimmed
    aggregate_result.texto_extracto_added_from_traceability += chunk_result.texto_extracto_added_from_traceability
    aggregate_result.incidental_table_types_removed += chunk_result.incidental_table_types_removed
    aggregate_result.type_object_minting_prevented += chunk_result.type_object_minting_prevented
    aggregate_result.long_local_name_truncated += chunk_result.long_local_name_truncated
    aggregate_result.hash_due_to_weak_identity += chunk_result.hash_due_to_weak_identity
    aggregate_result.hash_due_to_collision += chunk_result.hash_due_to_collision
    aggregate_result.phrase_like_entities_purged += chunk_result.phrase_like_entities_purged
    aggregate_result.minted_assignments.update(chunk_result.minted_assignments)
    aggregate_result.purged_nodes.extend(chunk_result.purged_nodes)


def _validate_merge_input(
    graph: Graph,
    *,
    path: Path,
    vocabulary: SemanticVocabulary,
    rejected_inputs: list[dict[str, object]],
    warned_inputs: list[dict[str, object]],
) -> bool:
    validation = validate_abox_graph(graph, vocabulary=vocabulary)
    blocking_failures = {
        key: value
        for key, value in validation.error_categories.items()
        if key in CHUNK_REJECTION_FAILURES
    }
    if blocking_failures:
        rejected_inputs.append(
            {
                "path": str(path),
                "failures": blocking_failures,
                "sample_invalid_classes": validation.invalid_class_values[:5],
                "sample_invalid_predicates": validation.invalid_predicate_values[:5],
                "sample_individuals_used_as_class": validation.sample_individuals_used_as_class[:5],
                "sample_blank_node_entities": validation.sample_blank_node_entities[:5],
                "sample_file_uri_entities": validation.sample_file_uri_entities[:5],
            }
        )
        return False

    nonblocking_failures = {
        key: value
        for key, value in validation.error_categories.items()
        if key not in CHUNK_REJECTION_FAILURES
    }
    if nonblocking_failures:
        warned_inputs.append(
            {
                "path": str(path),
                "warnings": nonblocking_failures,
                "sample_subjects_without_type": validation.sample_subjects_without_type[:5],
                "sample_subjects_without_traceability": validation.sample_subjects_without_traceability[:5],
                "sample_long_local_name_entities": validation.sample_long_local_name_entities[:5],
            }
        )
    return True


def write_rejection_report(path: Path, rejected_inputs: list[dict[str, object]], warned_inputs: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": {
            "rejected_count": len(rejected_inputs),
            "warned_count": len(warned_inputs),
            "hard_failure_keys": sorted(CHUNK_REJECTION_FAILURES),
        },
        "rejected": rejected_inputs,
        "warned": warned_inputs,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_marked_chunks_report(path: Path, warned_inputs: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": {
            "marked_count": len(warned_inputs),
            "note": "Chunks accepted into the merge with non-blocking semantic diagnostics.",
        },
        "chunks": warned_inputs,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sanitize_final_merged_graph(graph: Graph, *, tbox_graph: Graph) -> tuple[Graph, SanitizationResult]:
    result = SanitizationResult()
    graph = downgrade_invalid_hex_binary_literals(graph, result=result)
    graph = infer_missing_types(graph, tbox_graph=tbox_graph, result=result)
    graph = drop_redundant_supertypes(graph, tbox_graph=tbox_graph, result=result)
    graph = drop_incidental_table_types(graph, result=result)
    graph = ensure_minimal_traceability(graph, result=result)
    graph = prune_or_scope_texto_extracto(graph, result=result)
    graph = purge_phrase_like_entities(graph, result=result)
    return graph, result


def merge_from_directory(
    input_dir: Path,
    *,
    tbox_graph: Graph,
    mint_registry: dict[str, str],
    vocabulary: SemanticVocabulary | None = None,
    rejected_inputs: list[dict[str, object]] | None = None,
    warned_inputs: list[dict[str, object]] | None = None,
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
    vocabulary = vocabulary or load_semantic_vocabulary(OPERATIONAL_TBOX_PATH)
    rejected_inputs = rejected_inputs if rejected_inputs is not None else []
    warned_inputs = warned_inputs if warned_inputs is not None else []

    print(f"Merging {len(archivos_ttl)} A-Box fragments from {input_dir} ...")
    for archivo in archivos_ttl:
        try:
            chunk_graph = load_ttl_graph(archivo)
            chunk_graph, chunk_result = sanitize_abox_graph(
                chunk_graph,
                tbox_graph=tbox_graph,
                mint_registry=mint_registry,
            )
            _collect_sanitization(aggregate_result, chunk_result)
            if not _validate_merge_input(
                chunk_graph,
                path=archivo,
                vocabulary=vocabulary,
                rejected_inputs=rejected_inputs,
                warned_inputs=warned_inputs,
            ):
                errores += 1
                continue
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
    vocabulary: SemanticVocabulary | None = None,
    rejected_inputs: list[dict[str, object]] | None = None,
    warned_inputs: list[dict[str, object]] | None = None,
) -> tuple[Graph, int, SanitizationResult]:
    grafo_unificado = Graph()
    exitos = 0
    aggregate_result = SanitizationResult()
    vocabulary = vocabulary or load_semantic_vocabulary(OPERATIONAL_TBOX_PATH)
    rejected_inputs = rejected_inputs if rejected_inputs is not None else []
    warned_inputs = warned_inputs if warned_inputs is not None else []
    for path in paths:
        if not path.exists():
            raise SystemExit(f"Error: Grafo A-Box requerido no encontrado - {path}")
        chunk_graph = load_ttl_graph(path)
        chunk_graph, chunk_result = sanitize_abox_graph(
            chunk_graph,
            tbox_graph=tbox_graph,
            mint_registry=mint_registry,
        )
        _collect_sanitization(aggregate_result, chunk_result)
        validation = validate_abox_graph(chunk_graph, vocabulary=vocabulary)
        if validation.error_categories:
            warned_inputs.append(
                {
                    "path": str(path),
                    "warnings": validation.error_categories,
                    "sample_invalid_classes": validation.invalid_class_values[:5],
                    "sample_invalid_predicates": validation.invalid_predicate_values[:5],
                    "sample_individuals_used_as_class": validation.sample_individuals_used_as_class[:5],
                    "sample_long_local_name_entities": validation.sample_long_local_name_entities[:5],
                }
            )
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
    vocabulary = load_semantic_vocabulary(OPERATIONAL_TBOX_PATH)
    mint_registry = load_mint_registry(ABOX_MINTED_ENTITY_REGISTRY_PATH)
    directory_sanitization = SanitizationResult()
    input_graph_sanitization = SanitizationResult()
    rejected_inputs: list[dict[str, object]] = []
    warned_inputs: list[dict[str, object]] = []

    if args.input_dir is not None:
        grafo_directorio, exitos, errores, directory_sanitization = merge_from_directory(
            args.input_dir,
            tbox_graph=tbox_graph,
            mint_registry=mint_registry,
            vocabulary=vocabulary,
            rejected_inputs=rejected_inputs,
            warned_inputs=warned_inputs,
        )
        grafo_unificado += grafo_directorio
        fuentes.append(str(args.input_dir))

    if input_graphs:
        grafo_extra, exitos_extra, input_graph_sanitization = merge_from_graphs(
            input_graphs,
            tbox_graph=tbox_graph,
            mint_registry=mint_registry,
            vocabulary=vocabulary,
            rejected_inputs=rejected_inputs,
            warned_inputs=warned_inputs,
        )
        grafo_unificado += grafo_extra
        exitos += exitos_extra
        fuentes.extend(str(path) for path in input_graphs)

    grafo_unificado, final_sanitization = sanitize_final_merged_graph(grafo_unificado, tbox_graph=tbox_graph)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    grafo_unificado.serialize(destination=args.output, format="turtle")
    save_mint_registry(mint_registry, ABOX_MINTED_ENTITY_REGISTRY_PATH)
    write_rejection_report(ABOX_MERGER_REJECTED_CHUNKS_PATH, rejected_inputs, warned_inputs)
    write_marked_chunks_report(ABOX_MERGER_MARKED_CHUNKS_PATH, warned_inputs)

    serialized_graph = load_ttl_graph(args.output)
    validate_merged_uri_consistency(serialized_graph, tbox_graph=tbox_graph, output_path=args.output)
    identifier_collision_report = report_identifier_collisions(serialized_graph)
    ABOX_MERGER_IDENTIFIER_COLLISIONS_PATH.write_text(
        json.dumps(identifier_collision_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("-" * 40)
    print("RESUMEN DE CONSOLIDACION A-BOX")
    print("-" * 40)
    print(f"Fuentes fusionadas   : {fuentes}")
    print(f"Entradas procesadas  : {exitos}")
    print(f"Entradas corruptas   : {errores}")
    print(f"IRIs saneadas por chunk: {directory_sanitization.minted_nodes}")
    print(f"IRIs saneadas por grafo fusionado: {input_graph_sanitization.minted_nodes}")
    print(f"Entradas rechazadas  : {len(rejected_inputs)}")
    print(f"Advertencias semanticas: {len(warned_inputs)}")
    print(f"Colisiones de identificador: {identifier_collision_report['total_collision_groups']}")
    print(f"Saneado final sin minting: {final_sanitization.to_manifest_summary()}")
    print(f"Tripletas totales    : {len(grafo_unificado)}")
    print(f"Archivo generado     : {args.output}")


if __name__ == "__main__":
    main()
