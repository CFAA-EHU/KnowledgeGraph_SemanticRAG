from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from artifact_contracts import OPERATIONAL_ABOX_PATH, OPERATIONAL_TBOX_PATH, PROCESSED_DATA_DIR

TBOX_ENRICHMENT_EVIDENCE_PATH = PROCESSED_DATA_DIR / "t_tbox_enrichment_evidence.json"
BASE_URI = "https://vocab.cfaa.eus/broaching/"


def _local_name(uri: URIRef | str) -> str:
    value = str(uri)
    return value.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _load_graph(path: Path) -> Graph:
    graph = Graph()
    graph.parse(path, format="turtle")
    return graph


def _declared_classes(tbox: Graph) -> set[URIRef]:
    return {subject for subject in tbox.subjects(RDF.type, OWL.Class) if isinstance(subject, URIRef)}


def _declared_properties(tbox: Graph, rdf_type: URIRef) -> set[URIRef]:
    return {subject for subject in tbox.subjects(RDF.type, rdf_type) if isinstance(subject, URIRef)}


def _type_counter(abox: Graph) -> Counter[URIRef]:
    return Counter(obj for obj in abox.objects(None, RDF.type) if isinstance(obj, URIRef))


def _property_counter(abox: Graph, object_properties: set[URIRef]) -> Counter[URIRef]:
    counter: Counter[URIRef] = Counter()
    for _subject, predicate, obj in abox:
        if predicate in object_properties and isinstance(obj, URIRef):
            counter[predicate] += 1
    return counter


def _predicate_type_pairs(
    abox: Graph,
    object_properties: set[URIRef],
    classes: set[URIRef],
) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for predicate in sorted(object_properties, key=str):
        pair_counter: Counter[tuple[str, str]] = Counter()
        source_counter: Counter[str] = Counter()
        target_counter: Counter[str] = Counter()
        triple_count = 0
        for subject, obj in abox.subject_objects(predicate):
            if not isinstance(subject, URIRef) or not isinstance(obj, URIRef):
                continue
            source_types = [type_uri for type_uri in abox.objects(subject, RDF.type) if isinstance(type_uri, URIRef) and type_uri in classes]
            target_types = [type_uri for type_uri in abox.objects(obj, RDF.type) if isinstance(type_uri, URIRef) and type_uri in classes]
            if not source_types or not target_types:
                continue
            triple_count += 1
            for source_type in source_types:
                source_counter[_local_name(source_type)] += 1
                for target_type in target_types:
                    target_counter[_local_name(target_type)] += 1
                    pair_counter[(_local_name(source_type), _local_name(target_type))] += 1
        payload[_local_name(predicate)] = {
            "triple_count_with_typed_endpoints": triple_count,
            "source_type_counts": dict(source_counter.most_common(10)),
            "target_type_counts": dict(target_counter.most_common(10)),
            "source_target_type_pairs": [
                {"source_type": source, "target_type": target, "count": count}
                for (source, target), count in pair_counter.most_common(20)
            ],
        }
    return payload


def _uniform_property_candidates(predicate_pairs: dict[str, dict[str, Any]], *, min_count: int = 3, min_ratio: float = 0.8) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for predicate, evidence in predicate_pairs.items():
        total = evidence["triple_count_with_typed_endpoints"]
        if total < min_count:
            continue
        source_counts = evidence["source_type_counts"]
        target_counts = evidence["target_type_counts"]
        if source_counts:
            source_type, source_count = next(iter(source_counts.items()))
            if source_count / total >= min_ratio:
                candidates.append(
                    {
                        "axiom_type": "rdfs:domain",
                        "property": predicate,
                        "class": source_type,
                        "support_count": source_count,
                        "typed_endpoint_count": total,
                        "support_ratio": round(source_count / total, 4),
                    }
                )
        if target_counts:
            target_type, target_count = next(iter(target_counts.items()))
            if target_count / total >= min_ratio:
                candidates.append(
                    {
                        "axiom_type": "rdfs:range",
                        "property": predicate,
                        "class": target_type,
                        "support_count": target_count,
                        "typed_endpoint_count": total,
                        "support_ratio": round(target_count / total, 4),
                    }
                )
    return candidates


def _confirmed_disjoint_candidates(classes: set[URIRef]) -> list[dict[str, Any]]:
    conservative_pairs = [
        ("Maquina", "Manual", "physical asset vs document artifact"),
        ("Maquina", "Directiva", "physical asset vs normative document"),
        ("Maquina", "PiezaRecambio", "whole machine vs replacement part"),
        ("Empresa", "Directiva", "organization vs normative document"),
        ("Alarma", "PlanMantenimiento", "runtime alarm vs maintenance plan"),
        ("CodigoError", "Figura", "error code vs document figure"),
    ]
    class_names = {_local_name(uri) for uri in classes}
    candidates = []
    for left, right, reason in conservative_pairs:
        if left in class_names and right in class_names:
            candidates.append(
                {
                    "left_class": left,
                    "right_class": right,
                    "reason": reason,
                    "status": "applicable",
                }
            )
        else:
            candidates.append(
                {
                    "left_class": left,
                    "right_class": right,
                    "reason": reason,
                    "status": "skipped_missing_class",
                    "missing_classes": sorted({name for name in (left, right) if name not in class_names}),
                }
            )
    return candidates


def build_tbox_enrichment_evidence(
    *,
    abox_path: Path = OPERATIONAL_ABOX_PATH,
    tbox_path: Path = OPERATIONAL_TBOX_PATH,
) -> dict[str, Any]:
    abox = _load_graph(abox_path)
    tbox = _load_graph(tbox_path)
    classes = _declared_classes(tbox)
    object_properties = _declared_properties(tbox, OWL.ObjectProperty)
    datatype_properties = _declared_properties(tbox, OWL.DatatypeProperty)
    type_counts = _type_counter(abox)
    property_counts = _property_counter(abox, object_properties)
    predicate_pairs = _predicate_type_pairs(abox, object_properties, classes)

    used_classes = {type_uri for type_uri, count in type_counts.items() if count > 0}
    used_object_properties = {predicate for predicate, count in property_counts.items() if count > 0}

    return {
        "summary": {
            "abox_path": str(abox_path),
            "tbox_path": str(tbox_path),
            "declared_class_count": len(classes),
            "used_declared_class_count": len(used_classes & classes),
            "unused_declared_class_count": len(classes - used_classes),
            "declared_object_property_count": len(object_properties),
            "used_object_property_count": len(used_object_properties),
            "declared_datatype_property_count": len(datatype_properties),
            "total_abox_triples": len(abox),
        },
        "classes_with_individuals": [
            {"class": _local_name(class_uri), "count": count}
            for class_uri, count in type_counts.most_common()
            if class_uri in classes
        ],
        "classes_without_individuals": sorted(_local_name(class_uri) for class_uri in classes - used_classes),
        "object_properties_used": [
            {"property": _local_name(predicate), "count": count}
            for predicate, count in property_counts.most_common()
        ],
        "object_properties_without_use": sorted(_local_name(predicate) for predicate in object_properties - used_object_properties),
        "predicate_type_evidence": predicate_pairs,
        "uniform_domain_range_candidates": _uniform_property_candidates(predicate_pairs),
        "disjointness_candidates": _confirmed_disjoint_candidates(classes),
        "applied_axiom_recommendations": [
            {
                "axiom_type": "rdfs:subClassOf",
                "subject": "Alarma",
                "object": "AvisoSeguridad",
                "reason": "Las alarmas son avisos/eventos de seguridad operacional y el A-Box usa ambas familias en preguntas de errores.",
                "risk": "low",
            },
            {
                "axiom_type": "rdfs:subClassOf",
                "subject": "DiagnosticoFallo",
                "object": "AvisoSeguridad",
                "reason": "Fault diagnostics are anomalous-condition signals used alongside errors and alarms.",
                "risk": "low",
            },
            {
                "axiom_type": "rdfs:subClassOf",
                "subject": "Esquema",
                "object": "Figura",
                "reason": "A schema is a graphical documentary representation; improves compatibility with ilustradoEn/detalladoEnEsquema without introducing new classes.",
                "risk": "low",
            },
            {
                "axiom_type": "owl:inverseOf",
                "subject": "compuestoPor",
                "object": "esComponenteDe",
                "reason": "Both properties already exist in the project runtime evidence only when declared; skipped unless both are present.",
                "risk": "skipped_if_missing",
            },
            {
                "axiom_type": "owl:disjointWith",
                "subject": "Maquina",
                "object": "Manual",
                "reason": "Physical machine and document manual should not be canonicalized as the same identity.",
                "risk": "low",
            },
            {
                "axiom_type": "owl:disjointWith",
                "subject": "Maquina",
                "object": "Directiva",
                "reason": "Physical machine and directive/normative artifact are identity-disjoint.",
                "risk": "low",
            },
            {
                "axiom_type": "owl:disjointWith",
                "subject": "Empresa",
                "object": "Directiva",
                "reason": "Organization and directive/normative artifact are identity-disjoint.",
                "risk": "low",
            },
        ],
    }


def main() -> None:
    evidence = build_tbox_enrichment_evidence()
    TBOX_ENRICHMENT_EVIDENCE_PATH.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"T-Box enrichment evidence written to {TBOX_ENRICHMENT_EVIDENCE_PATH}")


if __name__ == "__main__":
    main()
