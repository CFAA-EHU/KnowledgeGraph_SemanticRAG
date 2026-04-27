import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass

from rdflib import BNode, Graph, OWL, RDF, RDFS, URIRef

from artifact_contracts import ABOX_SEMANTIC_AUDIT_PATH, OPERATIONAL_ABOX_PATH, OPERATIONAL_TBOX_PATH

BASE_URI = "https://vocab.cfaa.eus/broaching/"
TEXTO_EXTRACTO = URIRef(BASE_URI + "textoExtracto")
IDENTIFICADOR = URIRef(BASE_URI + "identificador")
LOCAL_NAME_MAX_LENGTH = 100
LOCAL_NAME_HARD_FAILURE = False


@dataclass(frozen=True)
class SemanticVocabulary:
    classes: set[str]
    object_properties: set[str]
    datatype_properties: set[str]

    @property
    def allowed_predicates(self) -> set[str]:
        return set(self.object_properties).union(self.datatype_properties).union({str(RDF.type), str(RDFS.label)})


@dataclass
class SemanticValidationResult:
    ok: bool
    total_typed_subjects: int
    total_object_links: int
    invalid_class_assertions: int
    invalid_predicate_assertions: int
    subjects_without_type: int
    subjects_without_traceability: int
    weakly_linked_subjects: int
    blank_node_entities: int
    file_uri_entities: int
    redundant_type_assertions: int
    individual_used_as_class_assertions: int
    long_local_name_entities: int
    error_categories: dict[str, int]
    invalid_class_values: list[list[object]]
    invalid_predicate_values: list[list[object]]
    sample_subjects_without_type: list[str]
    sample_subjects_without_traceability: list[str]
    sample_weakly_linked_subjects: list[str]
    sample_blank_node_entities: list[str]
    sample_file_uri_entities: list[str]
    sample_redundant_type_entities: list[str]
    sample_individuals_used_as_class: list[str]
    sample_long_local_name_entities: list[str]

    def to_manifest_summary(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "total_typed_subjects": self.total_typed_subjects,
            "total_object_links": self.total_object_links,
            "invalid_class_assertions": self.invalid_class_assertions,
            "invalid_predicate_assertions": self.invalid_predicate_assertions,
            "subjects_without_type": self.subjects_without_type,
            "subjects_without_traceability": self.subjects_without_traceability,
            "weakly_linked_subjects": self.weakly_linked_subjects,
            "blank_node_entities": self.blank_node_entities,
            "file_uri_entities": self.file_uri_entities,
            "redundant_type_assertions": self.redundant_type_assertions,
            "individual_used_as_class_assertions": self.individual_used_as_class_assertions,
            "long_local_name_entities": self.long_local_name_entities,
            "error_categories": self.error_categories,
            "invalid_class_values": self.invalid_class_values[:10],
            "invalid_predicate_values": self.invalid_predicate_values[:10],
            "sample_subjects_without_type": self.sample_subjects_without_type[:10],
            "sample_subjects_without_traceability": self.sample_subjects_without_traceability[:10],
            "sample_weakly_linked_subjects": self.sample_weakly_linked_subjects[:10],
            "sample_blank_node_entities": self.sample_blank_node_entities[:10],
            "sample_file_uri_entities": self.sample_file_uri_entities[:10],
            "sample_redundant_type_entities": self.sample_redundant_type_entities[:10],
            "sample_individuals_used_as_class": self.sample_individuals_used_as_class[:10],
            "sample_long_local_name_entities": self.sample_long_local_name_entities[:10],
        }


def _local_name(uri: str) -> str:
    return uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def load_semantic_vocabulary(tbox_path: Path = OPERATIONAL_TBOX_PATH) -> SemanticVocabulary:
    graph = Graph()
    graph.parse(tbox_path, format="turtle")

    classes: set[str] = set()
    object_properties: set[str] = set()
    datatype_properties: set[str] = set()

    for subject, _, rdf_type in graph.triples((None, RDF.type, None)):
        subject_uri = str(subject)
        if rdf_type == OWL.Class:
            classes.add(subject_uri)
        elif rdf_type == OWL.ObjectProperty:
            object_properties.add(subject_uri)
        elif rdf_type == OWL.DatatypeProperty:
            datatype_properties.add(subject_uri)

    return SemanticVocabulary(
        classes=classes,
        object_properties=object_properties,
        datatype_properties=datatype_properties,
    )


def _build_subclass_closure(graph: Graph) -> dict[str, set[str]]:
    parents: dict[str, set[str]] = {}
    for child, _, parent in graph.triples((None, RDFS.subClassOf, None)):
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


def validate_abox_graph(graph: Graph, *, vocabulary: SemanticVocabulary | None = None) -> SemanticValidationResult:
    vocabulary = vocabulary or load_semantic_vocabulary()
    tbox_graph = Graph()
    tbox_graph.parse(OPERATIONAL_TBOX_PATH, format="turtle")
    subclass_closure = _build_subclass_closure(tbox_graph)

    typed_subjects = {subject for subject in graph.subjects(RDF.type, None) if isinstance(subject, URIRef)}
    described_subjects = {subject for subject in graph.subjects() if isinstance(subject, URIRef)}
    candidate_subjects = typed_subjects.union(described_subjects)
    blank_node_entities = sorted({str(subject) for subject in graph.subjects(RDF.type, None) if isinstance(subject, BNode)})
    blank_node_entities.extend(
        sorted(
            {
                str(node)
                for node in graph.all_nodes()
                if isinstance(node, BNode)
                and any(True for predicate in (RDFS.label, URIRef(BASE_URI + "identificador"), TEXTO_EXTRACTO) for _ in graph.objects(node, predicate))
            }
        )
    )
    blank_node_entities = sorted(set(blank_node_entities))
    file_uri_entities = sorted(
        {
            str(subject)
            for subject in candidate_subjects
            if str(subject).startswith("file:///")
        }
        | {
            str(obj)
            for obj in graph.objects()
            if isinstance(obj, URIRef) and str(obj).startswith("file:///")
        }
    )

    invalid_classes: Counter[str] = Counter()
    invalid_predicates: Counter[str] = Counter()
    individual_as_class: Counter[str] = Counter()
    subjects_without_type: list[str] = []
    subjects_without_traceability: list[str] = []
    weakly_linked_subjects: list[str] = []
    redundant_type_entities: list[str] = []
    redundant_type_assertions = 0
    long_local_name_entities: list[str] = []

    surface_predicates = {RDFS.label, IDENTIFICADOR, TEXTO_EXTRACTO}
    individual_uris: set[str] = {str(subject) for subject in typed_subjects}
    for predicate in surface_predicates:
        individual_uris.update(
            str(subject)
            for subject in graph.subjects(predicate, None)
            if isinstance(subject, URIRef)
        )

    outgoing_object_links: dict[URIRef, int] = Counter()
    incoming_object_links: dict[URIRef, int] = Counter()
    total_object_links = 0

    for subject, predicate, obj in graph:
        predicate_uri = str(predicate)
        if predicate_uri not in vocabulary.allowed_predicates:
            invalid_predicates[predicate_uri] += 1
        if predicate == RDF.type and isinstance(obj, URIRef) and str(obj) not in vocabulary.classes:
            invalid_classes[str(obj)] += 1
            obj_str = str(obj)
            local = _local_name(obj_str)
            is_hash_pattern = bool(re.search(r"_[0-9a-f]{10}$", local))
            is_known_individual = obj_str in individual_uris
            has_surfaces = any(True for surface_predicate in surface_predicates for _ in graph.objects(obj, surface_predicate))
            has_individual_local_name = bool(re.search(r"[A-Z][a-z]+\d+|_\d+$|\d{4,}", local))
            if is_hash_pattern or is_known_individual or has_surfaces or has_individual_local_name:
                individual_as_class[obj_str] += 1
        if predicate != RDF.type and isinstance(subject, URIRef) and isinstance(obj, URIRef):
            outgoing_object_links[subject] += 1
            incoming_object_links[obj] += 1
            total_object_links += 1

    for subject in sorted(candidate_subjects, key=str):
        if subject not in typed_subjects:
            subjects_without_type.append(str(subject))

        if subject in typed_subjects and not any(True for _ in graph.objects(subject, TEXTO_EXTRACTO)):
            subjects_without_traceability.append(str(subject))

        if subject in typed_subjects:
            useful_links = outgoing_object_links.get(subject, 0) + incoming_object_links.get(subject, 0)
            if useful_links == 0:
                weakly_linked_subjects.append(str(subject))

        subject_types = sorted({str(obj) for obj in graph.objects(subject, RDF.type) if isinstance(obj, URIRef)})
        for type_uri in subject_types:
            if any(type_uri in subclass_closure.get(other, set()) for other in subject_types if other != type_uri):
                redundant_type_assertions += 1
                redundant_type_entities.append(str(subject))
                break

        local = _local_name(str(subject))
        if len(local) > LOCAL_NAME_MAX_LENGTH:
            long_local_name_entities.append(str(subject))

    error_categories: dict[str, int] = {}
    if invalid_classes:
        error_categories["non_canonical_class"] = sum(invalid_classes.values())
    if invalid_predicates:
        error_categories["non_canonical_property"] = sum(invalid_predicates.values())
    if subjects_without_type:
        error_categories["missing_type"] = len(subjects_without_type)
    if subjects_without_traceability:
        error_categories["missing_traceability"] = len(subjects_without_traceability)
    if weakly_linked_subjects:
        error_categories["weak_linkage"] = len(weakly_linked_subjects)
    if blank_node_entities:
        error_categories["blank_node_entity"] = len(blank_node_entities)
    if file_uri_entities:
        error_categories["file_uri_entity"] = len(file_uri_entities)
    if redundant_type_assertions:
        error_categories["redundant_type_assertion"] = redundant_type_assertions
    if individual_as_class:
        error_categories["individual_used_as_class"] = sum(individual_as_class.values())
    if long_local_name_entities:
        error_categories["long_local_name"] = len(long_local_name_entities)
    if len(typed_subjects) > 1 and total_object_links == 0:
        error_categories["no_useful_links"] = len(typed_subjects)

    hard_failure_keys = {
        "non_canonical_class",
        "non_canonical_property",
        "missing_type",
        "missing_traceability",
        "blank_node_entity",
        "file_uri_entity",
        "redundant_type_assertion",
        "individual_used_as_class",
    }
    if LOCAL_NAME_HARD_FAILURE:
        hard_failure_keys.add("long_local_name")
    ok = not any(key in error_categories for key in hard_failure_keys)

    return SemanticValidationResult(
        ok=ok,
        total_typed_subjects=len(typed_subjects),
        total_object_links=total_object_links,
        invalid_class_assertions=sum(invalid_classes.values()),
        invalid_predicate_assertions=sum(invalid_predicates.values()),
        subjects_without_type=len(subjects_without_type),
        subjects_without_traceability=len(subjects_without_traceability),
        weakly_linked_subjects=len(weakly_linked_subjects),
        blank_node_entities=len(blank_node_entities),
        file_uri_entities=len(file_uri_entities),
        redundant_type_assertions=redundant_type_assertions,
        individual_used_as_class_assertions=sum(individual_as_class.values()),
        long_local_name_entities=len(long_local_name_entities),
        error_categories=error_categories,
        invalid_class_values=[[ _local_name(uri), count ] for uri, count in invalid_classes.most_common(15)],
        invalid_predicate_values=[[ _local_name(uri), count ] for uri, count in invalid_predicates.most_common(15)],
        sample_subjects_without_type=[_local_name(uri) for uri in subjects_without_type[:15]],
        sample_subjects_without_traceability=[_local_name(uri) for uri in subjects_without_traceability[:15]],
        sample_weakly_linked_subjects=[_local_name(uri) for uri in weakly_linked_subjects[:15]],
        sample_blank_node_entities=blank_node_entities[:15],
        sample_file_uri_entities=[_local_name(uri) for uri in file_uri_entities[:15]],
        sample_redundant_type_entities=[_local_name(uri) for uri in redundant_type_entities[:15]],
        sample_individuals_used_as_class=[_local_name(uri) for uri, _count in individual_as_class.most_common(15)],
        sample_long_local_name_entities=[_local_name(uri) for uri in long_local_name_entities[:15]],
    )


def validate_ttl_text_semantics(ttl_data: str, *, vocabulary: SemanticVocabulary | None = None) -> SemanticValidationResult:
    graph = Graph()
    graph.parse(data=ttl_data, format="turtle")
    return validate_abox_graph(graph, vocabulary=vocabulary)


def validate_ttl_file_semantics(path: Path, *, vocabulary: SemanticVocabulary | None = None) -> SemanticValidationResult:
    graph = Graph()
    graph.parse(path, format="turtle")
    return validate_abox_graph(graph, vocabulary=vocabulary)


def summarize_semantic_result(result: SemanticValidationResult) -> str:
    if result.ok:
        return (
            f"OK semantico: {result.total_typed_subjects} individuos tipados, "
            f"{result.total_object_links} enlaces utiles."
        )

    fragments: list[str] = []
    if result.invalid_class_assertions:
        fragments.append(f"clases no canonicas={result.invalid_class_assertions}")
    if result.invalid_predicate_assertions:
        fragments.append(f"propiedades no canonicas={result.invalid_predicate_assertions}")
    if result.subjects_without_type:
        fragments.append(f"sin tipo={result.subjects_without_type}")
    if result.subjects_without_traceability:
        fragments.append(f"sin textoExtracto={result.subjects_without_traceability}")
    if result.error_categories.get("no_useful_links"):
        fragments.append("sin enlaces utiles")
    if result.weakly_linked_subjects:
        fragments.append(f"nodos poco enlazados={result.weakly_linked_subjects}")
    if result.blank_node_entities:
        fragments.append(f"blank_nodes_de_dominio={result.blank_node_entities}")
    if result.file_uri_entities:
        fragments.append(f"file_uris={result.file_uri_entities}")
    if result.redundant_type_assertions:
        fragments.append(f"tipos_redundantes={result.redundant_type_assertions}")
    if result.individual_used_as_class_assertions:
        fragments.append(f"individuos_usados_como_clase={result.individual_used_as_class_assertions}")
    if result.long_local_name_entities:
        fragments.append(f"local_names_largos={result.long_local_name_entities}")
    return "A-Box semanticamente invalida: " + ", ".join(fragments)


def audit_graph_to_json(abox_path: Path = OPERATIONAL_ABOX_PATH, *, tbox_path: Path = OPERATIONAL_TBOX_PATH, output_path: Path = ABOX_SEMANTIC_AUDIT_PATH) -> dict[str, object]:
    graph = Graph()
    graph.parse(abox_path, format="turtle")
    vocabulary = load_semantic_vocabulary(tbox_path)
    result = validate_abox_graph(graph, vocabulary=vocabulary)

    payload = {
        "abox_path": str(abox_path),
        "tbox_path": str(tbox_path),
        "acceptable_for_phase": result.ok,
        "acceptance_criteria": {
            "hard_fail": [
                "non_canonical_class",
                "non_canonical_property",
                "missing_type",
                "missing_traceability",
                "blank_node_entity",
                "file_uri_entity",
                "redundant_type_assertion",
                "individual_used_as_class",
            ],
            "diagnostic_only": [
                "weak_linkage",
                "no_useful_links",
                "long_local_name",
            ],
        },
        "summary": result.to_manifest_summary(),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auditoria semantica ligera de la A-Box operativa.")
    parser.add_argument("--abox-path", type=Path, default=OPERATIONAL_ABOX_PATH)
    parser.add_argument("--tbox-path", type=Path, default=OPERATIONAL_TBOX_PATH)
    parser.add_argument("--output-path", type=Path, default=ABOX_SEMANTIC_AUDIT_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    payload = audit_graph_to_json(args.abox_path, tbox_path=args.tbox_path, output_path=args.output_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
