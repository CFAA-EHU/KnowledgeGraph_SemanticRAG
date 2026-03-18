import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass

from rdflib import Graph, OWL, RDF, RDFS, URIRef

from artifact_contracts import ABOX_SEMANTIC_AUDIT_PATH, OPERATIONAL_ABOX_PATH, OPERATIONAL_TBOX_PATH

BASE_URI = "https://vocab.cfaa.eus/broaching/"
TEXTO_EXTRACTO = URIRef(BASE_URI + "textoExtracto")


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
    error_categories: dict[str, int]
    invalid_class_values: list[list[object]]
    invalid_predicate_values: list[list[object]]
    sample_subjects_without_type: list[str]
    sample_subjects_without_traceability: list[str]
    sample_weakly_linked_subjects: list[str]

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
            "error_categories": self.error_categories,
            "invalid_class_values": self.invalid_class_values[:10],
            "invalid_predicate_values": self.invalid_predicate_values[:10],
            "sample_subjects_without_type": self.sample_subjects_without_type[:10],
            "sample_subjects_without_traceability": self.sample_subjects_without_traceability[:10],
            "sample_weakly_linked_subjects": self.sample_weakly_linked_subjects[:10],
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


def validate_abox_graph(graph: Graph, *, vocabulary: SemanticVocabulary | None = None) -> SemanticValidationResult:
    vocabulary = vocabulary or load_semantic_vocabulary()

    typed_subjects = {subject for subject in graph.subjects(RDF.type, None) if isinstance(subject, URIRef)}
    described_subjects = {subject for subject in graph.subjects() if isinstance(subject, URIRef)}
    candidate_subjects = typed_subjects.union(described_subjects)

    invalid_classes: Counter[str] = Counter()
    invalid_predicates: Counter[str] = Counter()
    subjects_without_type: list[str] = []
    subjects_without_traceability: list[str] = []
    weakly_linked_subjects: list[str] = []

    outgoing_object_links: dict[URIRef, int] = Counter()
    incoming_object_links: dict[URIRef, int] = Counter()
    total_object_links = 0

    for subject, predicate, obj in graph:
        predicate_uri = str(predicate)
        if predicate_uri not in vocabulary.allowed_predicates:
            invalid_predicates[predicate_uri] += 1
        if predicate == RDF.type and isinstance(obj, URIRef) and str(obj) not in vocabulary.classes:
            invalid_classes[str(obj)] += 1
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
    if len(typed_subjects) > 1 and total_object_links == 0:
        error_categories["no_useful_links"] = len(typed_subjects)

    hard_failure_keys = {"non_canonical_class", "non_canonical_property", "missing_type", "missing_traceability"}
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
        error_categories=error_categories,
        invalid_class_values=[[ _local_name(uri), count ] for uri, count in invalid_classes.most_common(15)],
        invalid_predicate_values=[[ _local_name(uri), count ] for uri, count in invalid_predicates.most_common(15)],
        sample_subjects_without_type=[_local_name(uri) for uri in subjects_without_type[:15]],
        sample_subjects_without_traceability=[_local_name(uri) for uri in subjects_without_traceability[:15]],
        sample_weakly_linked_subjects=[_local_name(uri) for uri in weakly_linked_subjects[:15]],
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
            ],
            "diagnostic_only": [
                "weak_linkage",
                "no_useful_links",
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
