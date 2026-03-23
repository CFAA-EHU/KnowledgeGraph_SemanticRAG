from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

EX = Namespace("https://vocab.cfaa.eus/broaching/")
MIN_CONFIDENCE = 0.90


@dataclass
class LinkCompletionCandidate:
    family: str
    question_ids: list[str]
    question_examples: list[str]
    source_uri_candidates: list[str]
    target_uri_candidates: list[str]
    predicate_uri: str | None
    evidence_mode: str
    priority: int
    candidate_status: str
    confidence: float
    rule_id: str
    block_reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class LinkCompletion:
    source_uri: str
    predicate: str
    target_uri: str
    link_family: str
    evidence_type: str
    evidence_excerpt: str
    rule_id: str
    confidence: float
    question_ids: list[str] = field(default_factory=list)


FAMILY_CONFIG = {
    "declaration_signatory_link": {
        "priority": 1,
        "candidate_status": "whitelisted_active",
        "predicate_uri": str(EX.firmadoPor),
        "evidence_mode": "text",
        "rule_id": "link_rule_declaration_signatory",
    },
    "lockout_warning_link": {
        "priority": 2,
        "candidate_status": "whitelisted_active",
        "predicate_uri": str(EX.requiereAvisoSeguridad),
        "evidence_mode": "text",
        "rule_id": "link_rule_lockout_warning",
    },
    "panel_control_set_link": {
        "priority": 3,
        "candidate_status": "whitelisted_active",
        "predicate_uri": str(EX.tieneComponente),
        "evidence_mode": "structural",
        "rule_id": "link_rule_panel_control_set",
    },
    "machine_operating_modes_link": {
        "priority": 4,
        "candidate_status": "whitelisted_active",
        "predicate_uri": str(EX.disponeModoOperacion),
        "evidence_mode": "structural",
        "rule_id": "link_rule_machine_operating_modes",
    },
    "manual_greasing_task_link": {
        "priority": 5,
        "candidate_status": "whitelisted_active",
        "predicate_uri": str(EX.requiereMantenimiento),
        "evidence_mode": "structural",
        "rule_id": "link_rule_manual_greasing_task",
    },
    "emergency_button_usage_condition": {
        "priority": 6,
        "candidate_status": "whitelisted_blocked",
        "predicate_uri": None,
        "evidence_mode": "text",
        "rule_id": "link_rule_emergency_button_usage_blocked",
        "block_reason": "no_unique_condition_node",
    },
    "operator_ppe_requirement": {
        "priority": 7,
        "candidate_status": "whitelisted_blocked",
        "predicate_uri": None,
        "evidence_mode": "structural",
        "rule_id": "link_rule_operator_ppe_blocked",
        "block_reason": "overloaded_source_entity",
    },
}


def _load_json(payload_or_path: Any) -> Any:
    if isinstance(payload_or_path, (str, Path)):
        return json.loads(Path(payload_or_path).read_text(encoding="utf-8"))
    return payload_or_path


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9@/_\-.]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_uri(uri: str) -> str:
    return str(uri).split("/")[-1].split("#")[-1]


def _iter_entity_uris(graph: Graph) -> list[str]:
    return sorted({str(subject) for subject in graph.subjects() if isinstance(subject, URIRef)})


def _entity_text_values(graph: Graph, uri: str) -> list[str]:
    subject = URIRef(uri)
    values: list[str] = []
    for _, predicate, obj in graph.triples((subject, None, None)):
        if isinstance(obj, URIRef):
            continue
        if predicate in {RDFS.label, EX.identificador, EX.textoExtracto, EX.valor}:
            literal = str(obj).strip()
            if literal and literal not in values:
                values.append(literal)
    return values


def _entity_types(graph: Graph, uri: str) -> list[str]:
    subject = URIRef(uri)
    return sorted(
        {normalize_uri(obj) for _, _, obj in graph.triples((subject, RDF.type, None)) if isinstance(obj, URIRef)}
    )


def _find_unique_by_local_name(graph: Graph, local_name: str) -> str | None:
    matches = [uri for uri in _iter_entity_uris(graph) if normalize_uri(uri) == local_name]
    return matches[0] if len(matches) == 1 else None


def _find_by_text(graph: Graph, *, type_name: str | None = None, required_tokens: list[str], unique: bool = True) -> list[str]:
    matches: list[str] = []
    required = [normalize_text(token) for token in required_tokens if token]
    for uri in _iter_entity_uris(graph):
        if type_name and type_name not in _entity_types(graph, uri):
            continue
        text_blob = normalize_text(" ".join(_entity_text_values(graph, uri)))
        if all(token in text_blob for token in required):
            matches.append(uri)
    if unique:
        return matches[:1] if len(matches) == 1 else []
    return matches


def _pick_excerpt(graph: Graph, uri: str, required_tokens: list[str]) -> str:
    required = [normalize_text(token) for token in required_tokens if token]
    for value in _entity_text_values(graph, uri):
        normalized = normalize_text(value)
        if all(token in normalized for token in required):
            return value
    values = _entity_text_values(graph, uri)
    return values[0] if values else ""


def _classify_family(question: str) -> str | None:
    normalized = normalize_text(question)
    if "quien firma" in normalized and "declaracion ce" in normalized:
        return "declaration_signatory_link"
    if "consignar" in normalized and "interruptor general" in normalized:
        return "lockout_warning_link"
    if "botones principales" in normalized and "panel operador" in normalized:
        return "panel_control_set_link"
    if "modos de trabajo principales" in normalized:
        return "machine_operating_modes_link"
    if "engrase manual" in normalized and ("50 horas" in normalized or "50 h" in normalized):
        return "manual_greasing_task_link"
    if "pulsador de parada de emergencia" in normalized and "cuando" in normalized:
        return "emergency_button_usage_condition"
    if "equipo de proteccion personal" in normalized:
        return "operator_ppe_requirement"
    return None


def _build_family_candidate(graph: Graph, family: str, grouped_results: list[dict[str, Any]]) -> LinkCompletionCandidate:
    config = FAMILY_CONFIG[family]
    question_ids = [item["question_id"] for item in grouped_results]
    question_examples = [item["question"] for item in grouped_results]
    evidence: dict[str, Any] = {"questions": question_examples}
    source_candidates: list[str] = []
    target_candidates: list[str] = []
    confidence = 0.0
    block_reason = config.get("block_reason")

    if family == "declaration_signatory_link":
        source = _find_unique_by_local_name(graph, "Directiva2006_42_CE")
        target_matches = _find_by_text(graph, type_name="Personal", required_tokens=["datos del signatario", "director ejecutivo"], unique=True)
        target = target_matches[0] if target_matches else None
        if source and target:
            source_candidates = [source]
            target_candidates = [target]
            confidence = 0.97
            evidence["source_excerpt"] = _pick_excerpt(graph, source, ["2006/42/ce"])
            evidence["target_excerpt"] = _pick_excerpt(graph, target, ["datos del signatario", "director ejecutivo"])
            evidence["target_types"] = _entity_types(graph, target)
        else:
            block_reason = block_reason or "missing_unique_source_or_target"

    elif family == "lockout_warning_link":
        source = _find_unique_by_local_name(graph, "InterruptorGeneralArmarioElectrico")
        target = _find_unique_by_local_name(graph, "AvisoConsignacion")
        if source and target:
            source_candidates = [source]
            target_candidates = [target]
            confidence = 0.96
            evidence["source_excerpt"] = _pick_excerpt(graph, source, ["candado"])
            evidence["target_excerpt"] = _pick_excerpt(graph, target, ["cartel de advertencia", "candado"])
            evidence["target_types"] = _entity_types(graph, target)
        else:
            block_reason = block_reason or "missing_unique_source_or_target"

    elif family == "panel_control_set_link":
        source = _find_unique_by_local_name(graph, "PanelOperador")
        target_names = [
            "TeclaAperturaPuertas",
            "TeclaEnablePuertas",
            "TeclaMarchaCiclo",
            "TeclaParoServicio",
            "TeclaPuestaEnServicio",
            "TeclaSetup",
            "Selector51XS1",
        ]
        targets = [uri for name in target_names if (uri := _find_unique_by_local_name(graph, name))]
        if source and len(targets) == len(target_names):
            source_candidates = [source]
            target_candidates = targets
            confidence = 0.94
            evidence["source_excerpt"] = _pick_excerpt(graph, source, ["parada emergencia", "marcha ciclo", "apertura puertas"])
            evidence["target_types"] = {uri: _entity_types(graph, uri) for uri in targets}
        else:
            block_reason = block_reason or "missing_unique_panel_controls"

    elif family == "machine_operating_modes_link":
        source = _find_unique_by_local_name(graph, "MaquinaBrochadoExterior_18")
        target_names = ["ModoAutomatico", "ModoAutomaticoCargaDescargaManual", "ModoManual89"]
        targets = [uri for name in target_names if (uri := _find_unique_by_local_name(graph, name))]
        if source and len(targets) == len(target_names):
            source_candidates = [source]
            target_candidates = targets
            confidence = 0.93
            evidence["source_excerpt"] = _pick_excerpt(graph, source, ["brochado exterior"])
            evidence["target_types"] = {uri: _entity_types(graph, uri) for uri in targets}
            evidence["target_excerpts"] = {uri: _entity_text_values(graph, uri)[:2] for uri in targets}
        else:
            block_reason = block_reason or "missing_unique_mode_targets"

    elif family == "manual_greasing_task_link":
        source = _find_unique_by_local_name(graph, "CentralitaEngraseManual_104")
        target = _find_unique_by_local_name(graph, "TareaMantenimiento_AccionarBombeoEngraseManual")
        if source and target:
            source_candidates = [source]
            target_candidates = [target]
            confidence = 0.95
            evidence["source_excerpt"] = _pick_excerpt(graph, source, ["engrase manual", "iso 3498 g220"])
            evidence["target_excerpt"] = _pick_excerpt(graph, target, ["accionar el bombeo de engrase manual"])
            evidence["target_types"] = _entity_types(graph, target)
        else:
            block_reason = block_reason or "missing_unique_source_or_target"

    elif family == "emergency_button_usage_condition":
        source = _find_unique_by_local_name(graph, "PulsadorParadaEmergencia")
        if source:
            source_candidates = [source]
            evidence["source_excerpt"] = _pick_excerpt(graph, source, ["parada de emergencia"])
        target_candidates = _find_by_text(graph, required_tokens=["solo se debe usar", "peligro de lesiones"], unique=False)
        block_reason = "no_unique_condition_node"

    elif family == "operator_ppe_requirement":
        source = _find_unique_by_local_name(graph, "PanelOperadorVistaExterior")
        if source:
            source_candidates = [source]
            evidence["source_excerpt"] = _pick_excerpt(graph, source, ["equipo para la seguridad personal"])
        for name in ["EPI_GafasSeguridad", "EPI_Guantes"]:
            target = _find_unique_by_local_name(graph, name)
            if target:
                target_candidates.append(target)
        block_reason = "overloaded_source_entity"

    status = config["candidate_status"]
    if status == "whitelisted_active" and (not source_candidates or not target_candidates or confidence < MIN_CONFIDENCE):
        status = "whitelisted_blocked"
        if not block_reason:
            block_reason = "confidence_below_threshold_or_missing_target"
        confidence = 0.0

    return LinkCompletionCandidate(
        family=family,
        question_ids=question_ids,
        question_examples=question_examples,
        source_uri_candidates=source_candidates,
        target_uri_candidates=target_candidates,
        predicate_uri=config["predicate_uri"],
        evidence_mode=config["evidence_mode"],
        priority=config["priority"],
        candidate_status=status,
        confidence=round(confidence, 4),
        rule_id=config["rule_id"],
        block_reason=block_reason,
        evidence=evidence,
    )


def build_link_completion_candidates(
    enriched_graph: Graph,
    sandbox_summary: Any,
    sandbox_report: Any,
    enrichment_decision: Any,
    sandbox_candidates: Any | None = None,
) -> list[LinkCompletionCandidate]:
    sandbox_summary = _load_json(sandbox_summary)
    sandbox_report = _load_json(sandbox_report)
    enrichment_decision = _load_json(enrichment_decision)
    _ = _load_json(sandbox_candidates) if sandbox_candidates is not None else None

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in sandbox_report.get("results", []):
        family = _classify_family(item.get("question", ""))
        if not family or family not in FAMILY_CONFIG:
            continue
        grouped.setdefault(family, []).append(item)

    candidates = [
        _build_family_candidate(enriched_graph, family, grouped[family])
        for family in FAMILY_CONFIG
        if family in grouped
    ]
    candidates.sort(key=lambda item: (item.priority, item.family))
    return candidates


def detect_residual_links(graph: Graph, candidates: list[LinkCompletionCandidate]) -> list[LinkCompletion]:
    links: list[LinkCompletion] = []
    for candidate in candidates:
        if candidate.candidate_status != "whitelisted_active":
            continue
        if candidate.confidence < MIN_CONFIDENCE:
            continue
        if not candidate.predicate_uri:
            continue
        if len(candidate.source_uri_candidates) != 1:
            continue
        source_uri = candidate.source_uri_candidates[0]
        evidence_excerpt = str(candidate.evidence.get("target_excerpt") or candidate.evidence.get("source_excerpt") or "")
        for target_uri in candidate.target_uri_candidates:
            links.append(
                LinkCompletion(
                    source_uri=source_uri,
                    predicate=candidate.predicate_uri,
                    target_uri=target_uri,
                    link_family=candidate.family,
                    evidence_type=candidate.evidence_mode,
                    evidence_excerpt=evidence_excerpt,
                    rule_id=candidate.rule_id,
                    confidence=candidate.confidence,
                    question_ids=list(candidate.question_ids),
                )
            )
    links.sort(key=lambda item: (item.link_family, item.source_uri, item.target_uri))
    return links


def candidates_to_jsonable(candidates: list[LinkCompletionCandidate]) -> list[dict[str, Any]]:
    return [asdict(item) for item in candidates]


def links_to_jsonable(links: list[LinkCompletion]) -> list[dict[str, Any]]:
    return [asdict(item) for item in links]


def _extract_eval_summary(report: Any) -> dict[str, Any]:
    report = _load_json(report)
    summary = report.get("summary", report)
    if "successful_questions" in summary:
        return {
            "successful_questions": summary.get("successful_questions"),
            "total_questions": summary.get("total_questions"),
            "avg_precision": summary.get("avg_precision"),
            "avg_recall": summary.get("avg_recall"),
            "fallback_count": summary.get("fallback_count"),
            "abox_path": summary.get("abox_path"),
        }
    return summary


def build_link_completion_eval_report(
    baseline_decision: Any,
    current_summary: Any,
    current_decision: Any,
    qa_canonical_report: Any,
    qa_multihop_report: Any,
    link_completion_report: Any,
) -> dict[str, Any]:
    baseline_decision = _load_json(baseline_decision)
    current_summary = _load_json(current_summary)
    current_decision = _load_json(current_decision)
    link_completion_report = _load_json(link_completion_report)

    baseline_counts = baseline_decision.get("summary", {}).get("current_structural_gap_counts", {})
    current_counts = current_summary.get("summary", {}).get("structural_gap_counts", {})
    baseline_promotable = baseline_decision.get("summary", {}).get("promotable_question_ids", [])
    current_promotable = current_decision.get("promotable_question_ids", [])

    return {
        "summary": {
            "baseline_stage": baseline_decision.get("summary", {}).get("current_stage", "t18_post_enrichment"),
            "current_stage": "t19_post_link_completion",
            "baseline_structural_gap_counts": baseline_counts,
            "current_structural_gap_counts": current_counts,
            "focus_category_delta": {
                "graph_linking_gap": current_counts.get("graph_linking_gap", 0) - baseline_counts.get("graph_linking_gap", 0),
                "missing_value_surface": current_counts.get("missing_value_surface", 0) - baseline_counts.get("missing_value_surface", 0),
                "synthesis_surface_gap": current_counts.get("synthesis_surface_gap", 0) - baseline_counts.get("synthesis_surface_gap", 0),
            },
            "baseline_promotable_count": len(baseline_promotable),
            "current_promotable_count": len(current_promotable),
            "qa_canonical": _extract_eval_summary(qa_canonical_report),
            "qa_multihop": _extract_eval_summary(qa_multihop_report),
            "link_completion_artifacts": {
                "added_link_count": link_completion_report.get("summary", {}).get("added_link_count", 0),
                "added_families": link_completion_report.get("summary", {}).get("added_family_count", 0),
                "added_targets": link_completion_report.get("summary", {}).get("added_target_count", 0),
                "output_triples": link_completion_report.get("summary", {}).get("output_triples", 0),
            },
        },
        "assessment": {
            "qa_canonical_no_regression": _extract_eval_summary(qa_canonical_report).get("successful_questions") == _extract_eval_summary(qa_canonical_report).get("total_questions"),
            "qa_multihop_no_regression": _extract_eval_summary(qa_multihop_report).get("successful_questions") == _extract_eval_summary(qa_multihop_report).get("total_questions"),
            "graph_linking_gap_improved": current_counts.get("graph_linking_gap", 0) < baseline_counts.get("graph_linking_gap", 0),
            "missing_value_surface_improved": current_counts.get("missing_value_surface", 0) <= baseline_counts.get("missing_value_surface", 0),
            "synthesis_surface_gap_not_worse": current_counts.get("synthesis_surface_gap", 0) <= baseline_counts.get("synthesis_surface_gap", 0),
        },
    }
