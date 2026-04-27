from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

EX = Namespace("https://vocab.cfaa.eus/broaching/")
SURFACE_PREDICATE_URIS = {
    "label": RDFS.label,
    "identificador": EX.identificador,
    "textoExtracto": EX.textoExtracto,
    "valor": EX.valor,
}
SUPPORTED_GAPS = {"graph_linking_gap": 1, "missing_value_surface": 2, "synthesis_surface_gap": 3}
STOPWORDS = {
    "de", "la", "el", "los", "las", "del", "para", "por", "que", "una", "uno", "con", "sin",
    "segun", "sobre", "esta", "este", "estos", "estas", "cual", "donde", "quien", "como", "manual",
    "maquina", "maquinas", "indicado", "indicada", "mencionada", "respecto", "debe", "deben", "tipo",
    "informacion", "durante", "principales", "principal", "sistema", "trabajo", "modo", "modos",
}


@dataclass
class EnrichmentCandidate:
    question_id: str
    question: str
    expected_answer_text: str
    structural_gap_category: str
    priority: int
    plan_family: str | None
    chosen_entity_uri: str
    chosen_entity_types: list[str] = field(default_factory=list)
    chosen_best_surface_literal: str | None = None
    chosen_best_surface_score: float = 0.0
    target_uri: str | None = None
    target_types: list[str] = field(default_factory=list)
    target_best_surface_literal: str | None = None
    target_alignment_score: float = 0.0
    candidate_rule_hint: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class LinkEnrichment:
    source_uri: str
    predicate_uri: str
    target_uri: str
    enrichment_reason: str
    rule_id: str
    question_ids: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class SurfaceEnrichment:
    entity_uri: str
    added_property_uri: str
    added_value: str
    surface_type: str
    rule_id: str
    question_ids: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


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


def _token_overlap(a: str, b: str) -> float:
    a_tokens = {token for token in normalize_text(a).split() if len(token) >= 3}
    b_tokens = {token for token in normalize_text(b).split() if len(token) >= 3}
    return len(a_tokens & b_tokens) / max(len(a_tokens), 1) if a_tokens else 0.0


def _string_similarity(a: str, b: str) -> float:
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)
    return SequenceMatcher(None, a_norm, b_norm).ratio() if a_norm and b_norm else 0.0


def _significant_tokens(*values: str) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for token in normalize_text(value).split():
            if len(token) >= 3 and token not in STOPWORDS:
                tokens.add(token)
    return tokens


def extract_structured_values(text: str) -> list[str]:
    patterns = [
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        r"\b\d{4}/\d{2}/[A-Z]{2}\b",
        r"\biso\s*3498\s*(?:[- ]?[a-z0-9]+)?\b",
        r"\blue\+?\d+(?:-\d+)+\b",
        r"\bcada\s+\d+\s*h\b",
        r"\b\d+(?:[.,]\d+)?\s*l\b",
        r"\b\d+(?:[.,]\d+)?\s*volt\b",
        r"\b\d+(?:[.,]\d+)?\s*hz\b",
        r"\b\d+(?:[.,]\d+)?\s*cst\b",
    ]
    values: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text or "", re.I):
            cleaned = re.sub(r"\s+", " ", match).strip()
            if cleaned and cleaned not in values:
                values.append(cleaned)
    return values


def humanize_local_name(local_name: str) -> str:
    value = re.sub(r"_\d+(?:_\d+)*$", "", local_name or "")
    value = value.replace("_", " ")
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    value = re.sub(r"([A-Za-z])(\d)", r"\1 \2", value)
    value = re.sub(r"(\d)([A-Za-z])", r"\1 \2", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:1].upper() + value[1:] if value else ""


def split_text_fragments(text: str) -> list[str]:
    parts: list[str] = []
    for part in re.split(r"[\n\r|;:]+|(?<=[.!?])\s+", text or ""):
        cleaned = re.sub(r"\s+", " ", part).strip(" .;:-")
        if 8 <= len(cleaned) <= 220 and cleaned not in parts:
            parts.append(cleaned)
    return parts


def _preferred_surface_score(value: str, expected_answer: str) -> float:
    normalized = normalize_text(value)
    tokens = normalized.split()
    score = _token_overlap(expected_answer, value) + _string_similarity(expected_answer, value)
    structured_values = extract_structured_values(value)
    score += len(structured_values) * 0.35
    if 12 <= len(value) <= 120:
        score += 0.15
    if any(tag in normalized for tag in ["directiva", "cargo", "firma", "panel operador", "aceite", "grasa", "capacidad", "cada 50 h", "presion general de aire", "380 volt", "50 hz"]):
        score += 0.2
    if len(tokens) <= 2 and not structured_values:
        score -= 0.25
    if value.isupper() and len(tokens) <= 4:
        score -= 0.25
    return round(score, 4)


def describe_entity(graph: Graph, uri: str) -> dict[str, Any]:
    subject = URIRef(uri)
    types, labels, identifiers, texts, values, targets, predicates = [], [], [], [], [], [], []
    for _, predicate, obj in graph.triples((subject, None, None)):
        predicate_local = normalize_uri(predicate)
        predicates.append(predicate_local)
        if predicate == RDF.type and isinstance(obj, URIRef):
            types.append(normalize_uri(obj))
        elif isinstance(obj, URIRef):
            targets.append(str(obj))
        else:
            literal_value = str(obj)
            if predicate == RDFS.label:
                labels.append(literal_value)
            elif predicate_local == "identificador":
                identifiers.append(literal_value)
            elif predicate_local == "textoExtracto":
                texts.append(literal_value)
            elif predicate_local == "valor":
                values.append(literal_value)
    return {
        "uri": uri,
        "local_name": normalize_uri(uri),
        "types": types,
        "labels": labels,
        "identifiers": identifiers,
        "text_extracts": texts,
        "values": values,
        "incoming_count": sum(1 for _ in graph.subject_predicates(subject)),
        "outgoing_targets": targets,
        "outgoing_predicates": predicates,
    }


def best_surface_literal(description: dict[str, Any], expected_answer: str) -> tuple[str | None, float]:
    candidates = description.get("values", []) + description.get("identifiers", []) + description.get("labels", [])
    candidates += [fragment for text in description.get("text_extracts", []) for fragment in split_text_fragments(text)]
    humanized = humanize_local_name(description.get("local_name", ""))
    if humanized:
        candidates.append(humanized)
    best_value, best_score = None, -1.0
    for candidate in candidates:
        score = _preferred_surface_score(candidate, expected_answer)
        if score > best_score:
            best_value, best_score = candidate, score
    return best_value, round(max(best_score, 0.0), 4)


def _iter_entity_uris(graph: Graph) -> list[str]:
    return sorted({str(subject) for subject in graph.subjects() if isinstance(subject, URIRef)})


def _same_theme(a: dict[str, Any], b: dict[str, Any]) -> bool:
    shared = _significant_tokens(a.get("local_name", ""), *a.get("labels", []), *a.get("identifiers", []))
    shared &= _significant_tokens(b.get("local_name", ""), *b.get("labels", []), *b.get("identifiers", []))
    return bool(shared) or b.get("uri") in a.get("outgoing_targets", []) or a.get("uri") in b.get("outgoing_targets", [])


def search_graph_candidates(graph: Graph, expected_answer: str, question: str, chosen_uri: str, chosen_description: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    hits = []
    question_tokens = _significant_tokens(question, expected_answer)
    for uri in _iter_entity_uris(graph):
        if uri == chosen_uri:
            continue
        description = describe_entity(graph, uri)
        best_surface, score = best_surface_literal(description, expected_answer)
        if score <= 0.85:
            continue
        token_bonus = 0.1 * len(question_tokens & _significant_tokens(description.get("local_name", ""), *description.get("labels", []), *(best_surface and [best_surface] or [])))
        theme_bonus = 0.2 if _same_theme(chosen_description, description) else 0.0
        total = round(score + token_bonus + theme_bonus, 4)
        if total > 0.9:
            hits.append({"uri": uri, "types": description.get("types", []), "best_surface_literal": best_surface, "candidate_score": total, "candidate_reason": "graph_alignment_search"})
    hits.sort(key=lambda item: (-item["candidate_score"], normalize_uri(item["uri"])))
    return hits[:limit]

def _is_directive_like(description: dict[str, Any]) -> bool:
    return "Directiva" in description.get("types", []) or normalize_uri(description["uri"]).lower().startswith("directiva")


def _is_machine_like(description: dict[str, Any]) -> bool:
    return "Maquina" in description.get("types", []) or "maquina" in normalize_text(description.get("local_name", ""))


def _is_consumable_like(description: dict[str, Any]) -> bool:
    return "Consumible" in description.get("types", []) or any(token in normalize_text(description.get("local_name", "")) for token in ["aceite", "grasa", "fluido"])


def _is_maintenance_like(description: dict[str, Any]) -> bool:
    return any(token in normalize_text(description.get("local_name", "")) for token in ["mantenimiento", "engrase", "lubricacion", "tarea"])


def _is_interface_like(description: dict[str, Any]) -> bool:
    normalized = normalize_text(description.get("local_name", ""))
    return "InterfazUsuario" in description.get("types", []) or any(token in normalized for token in ["panel", "teclado", "selector", "pupitre"])


def _is_component_like(description: dict[str, Any]) -> bool:
    types = description.get("types", [])
    normalized = normalize_text(description.get("local_name", ""))
    return any(type_name.startswith("Componente") for type_name in types) or any(type_name in {"ElementoSeguridad", "SistemaSeguridad"} for type_name in types) or any(token in normalized for token in ["pulsador", "interruptor", "sensor", "motor", "valvula", "puerta", "cepillos", "modulo", "contact", "contactor"])


def _is_reference_like(description: dict[str, Any]) -> bool:
    normalized = normalize_text(description.get("local_name", ""))
    return any(token in normalized for token in ["figura", "plano", "esquema", "tabla", "capitulo"])


def _choose_target_candidate(graph: Graph, result_item: dict[str, Any], resolution_entry: dict[str, Any] | None) -> dict[str, Any] | None:
    chosen_uri = result_item.get("chosen_entity_uri")
    chosen_score = (resolution_entry or {}).get("chosen_best_surface_score") or 0.0
    candidate_entities = list((resolution_entry or {}).get("candidate_entities", []))
    candidate_entities.sort(key=lambda item: (-item.get("candidate_score", 0.0), normalize_uri(item.get("uri", ""))))
    if candidate_entities:
        best = candidate_entities[0]
        if best.get("candidate_score", 0.0) >= max(chosen_score + 0.2, 0.95):
            return best
    if not chosen_uri:
        return None
    chosen_description = describe_entity(graph, chosen_uri)
    searched = search_graph_candidates(graph, result_item.get("expected_answer_text", ""), result_item.get("question", ""), chosen_uri, chosen_description)
    return searched[0] if searched else None


def _candidate_rule_hint(question: str, source_desc: dict[str, Any], target_desc: dict[str, Any] | None) -> str | None:
    normalized = normalize_text(question)
    if target_desc and _is_directive_like(target_desc) and (_is_machine_like(source_desc) or "directiva" in normalized or "ce" in normalized):
        return "machine_directive_link"
    if target_desc and _is_consumable_like(target_desc) and any(token in normalized for token in ["aceite", "grasa", "consumible", "lubric", "engrase"]):
        return "consumable_bridge"
    if target_desc and (_is_interface_like(source_desc) or _is_interface_like(target_desc) or _is_component_like(source_desc) or _is_component_like(target_desc)) and any(token in normalized for token in ["panel", "boton", "pulsador", "selector", "teclado"]):
        return "panel_component_link"
    if target_desc and (_is_reference_like(source_desc) or _is_reference_like(target_desc)) and any(token in normalized for token in ["figura", "esquema", "plano", "referencia"]):
        return "reference_bridge"
    if target_desc and (_is_maintenance_like(source_desc) or _is_maintenance_like(target_desc)) and any(token in normalized for token in ["mantenimiento", "engrase", "50", "horas", "h"]):
        return "maintenance_bridge"
    return "surface_only"


def build_enrichment_corpus(graph: Graph, sandbox_summary: Any, sandbox_candidates: Any, sandbox_decision: Any, canonicalization_report: Any, sandbox_report: Any | None = None) -> dict[str, Any]:
    sandbox_summary = _load_json(sandbox_summary)
    sandbox_candidates = _load_json(sandbox_candidates)
    sandbox_decision = _load_json(sandbox_decision)
    canonicalization_report = _load_json(canonicalization_report)
    sandbox_report = _load_json(sandbox_report) if sandbox_report is not None else {"results": []}
    resolution_by_question = {item["question_id"]: item for item in sandbox_candidates.get("results", [])}
    canonical_touched = {selection.get("canonical_uri") for selection in canonicalization_report.get("selections", []) if selection.get("canonical_uri")}
    accepted, discarded = [], []
    for item in sandbox_report.get("results", []):
        gap = item.get("structural_gap_category")
        if gap not in SUPPORTED_GAPS:
            continue
        chosen_uri = item.get("chosen_entity_uri")
        if not chosen_uri:
            discarded.append({"question_id": item.get("question_id"), "reason": "missing_chosen_entity_uri"})
            continue
        chosen_description = describe_entity(graph, chosen_uri)
        chosen_surface, chosen_score = best_surface_literal(chosen_description, item.get("expected_answer_text", ""))
        resolution_entry = resolution_by_question.get(item.get("question_id"))
        target_candidate = _choose_target_candidate(graph, item, resolution_entry)
        target_description = describe_entity(graph, target_candidate["uri"]) if target_candidate else None
        accepted.append(
            EnrichmentCandidate(
                question_id=item["question_id"],
                question=item["question"],
                expected_answer_text=item.get("expected_answer_text", item.get("answer", "")),
                structural_gap_category=gap,
                priority=SUPPORTED_GAPS[gap],
                plan_family=item.get("plan_family"),
                chosen_entity_uri=chosen_uri,
                chosen_entity_types=chosen_description.get("types", []),
                chosen_best_surface_literal=chosen_surface,
                chosen_best_surface_score=chosen_score,
                target_uri=target_candidate.get("uri") if target_candidate else None,
                target_types=target_description.get("types", []) if target_description else [],
                target_best_surface_literal=target_candidate.get("best_surface_literal") if target_candidate else None,
                target_alignment_score=target_candidate.get("candidate_score", 0.0) if target_candidate else 0.0,
                candidate_rule_hint=_candidate_rule_hint(item.get("question", ""), chosen_description, target_description),
                evidence={
                    "answer_match_mode": item.get("answer_match_mode"),
                    "answer_surface_quality": item.get("answer_surface_quality"),
                    "answer_reference_gap": item.get("answer_reference_gap"),
                    "selected_evidence_count": item.get("selected_evidence_count", 0),
                    "recommendation_source": target_candidate.get("candidate_reason") if target_candidate else None,
                    "touched_by_canonicalization": chosen_uri in canonical_touched,
                },
            )
        )
    accepted.sort(key=lambda item: (item.priority, -(item.target_alignment_score or 0.0), item.question_id))
    return {
        "summary": {
            "baseline_dominant_issue": sandbox_decision.get("dominant_structural_gap_category"),
            "baseline_structural_gap_counts": sandbox_summary.get("summary", {}).get("structural_gap_counts", {}),
            "accepted_candidates": len(accepted),
            "discarded_candidates": len(discarded),
        },
        "accepted": accepted,
        "discarded": discarded,
    }


def _relation_exists(graph: Graph, source_uri: str, predicate_uri: str, target_uri: str) -> bool:
    return (URIRef(source_uri), URIRef(predicate_uri), URIRef(target_uri)) in graph


def _choose_link_relation(candidate: EnrichmentCandidate, source_desc: dict[str, Any], target_desc: dict[str, Any]) -> tuple[str, str, str, str] | None:
    question_text = normalize_text(candidate.question)
    if _is_directive_like(source_desc) and _is_machine_like(target_desc):
        source_desc, target_desc = target_desc, source_desc
    if _is_directive_like(target_desc) and _is_machine_like(source_desc):
        return source_desc["uri"], str(EX.cumpleNormativa), target_desc["uri"], "link_rule_machine_directive"
    if _is_consumable_like(source_desc) and not _is_consumable_like(target_desc):
        source_desc, target_desc = target_desc, source_desc
    if _is_consumable_like(target_desc) and any(token in question_text for token in ["aceite", "grasa", "consumible", "lubric", "engrase"]):
        return source_desc["uri"], str(EX.requiereConsumible), target_desc["uri"], "link_rule_consumable_requirement"
    if _is_maintenance_like(source_desc) and not _is_maintenance_like(target_desc):
        return target_desc["uri"], str(EX.requiereMantenimiento), source_desc["uri"], "link_rule_maintenance_bridge"
    if _is_maintenance_like(target_desc) and any(token in question_text for token in ["mantenimiento", "engrase", "50", "horas", "h"]):
        return source_desc["uri"], str(EX.requiereMantenimiento), target_desc["uri"], "link_rule_maintenance_bridge"
    if _is_interface_like(source_desc) and _is_component_like(target_desc):
        return source_desc["uri"], str(EX.tieneComponente), target_desc["uri"], "link_rule_interface_component"
    if _is_interface_like(target_desc) and _is_component_like(source_desc):
        return target_desc["uri"], str(EX.tieneComponente), source_desc["uri"], "link_rule_interface_component"
    if _is_reference_like(source_desc) or _is_reference_like(target_desc):
        predicate = str(EX.detalladoEnEsquema) if any(token in question_text for token in ["esquema", "plano"]) else str(EX.ilustradoEn)
        return source_desc["uri"], predicate, target_desc["uri"], "link_rule_reference_bridge"
    return None


def detect_link_enrichments(graph: Graph, corpus: list[EnrichmentCandidate]) -> list[LinkEnrichment]:
    aggregated: dict[tuple[str, str, str], LinkEnrichment] = {}
    for candidate in corpus:
        if not candidate.target_uri or candidate.structural_gap_category not in {"graph_linking_gap", "synthesis_surface_gap"}:
            continue
        source_desc = describe_entity(graph, candidate.chosen_entity_uri)
        target_desc = describe_entity(graph, candidate.target_uri)
        if not (_same_theme(source_desc, target_desc) or candidate.candidate_rule_hint in {"panel_component_link", "reference_bridge", "consumable_bridge", "maintenance_bridge", "machine_directive_link"}):
            continue
        relation = _choose_link_relation(candidate, source_desc, target_desc)
        if not relation:
            continue
        source_uri, predicate_uri, target_uri, rule_id = relation
        if source_uri == target_uri or _relation_exists(graph, source_uri, predicate_uri, target_uri):
            continue
        key = (source_uri, predicate_uri, target_uri)
        if key not in aggregated:
            aggregated[key] = LinkEnrichment(
                source_uri=source_uri,
                predicate_uri=predicate_uri,
                target_uri=target_uri,
                enrichment_reason=candidate.structural_gap_category,
                rule_id=rule_id,
                question_ids=[],
                evidence={"plan_families": [], "source_types": describe_entity(graph, source_uri).get("types", []), "target_types": describe_entity(graph, target_uri).get("types", [])},
            )
        if candidate.question_id not in aggregated[key].question_ids:
            aggregated[key].question_ids.append(candidate.question_id)
        if candidate.plan_family and candidate.plan_family not in aggregated[key].evidence["plan_families"]:
            aggregated[key].evidence["plan_families"].append(candidate.plan_family)
    return sorted(aggregated.values(), key=lambda item: (item.rule_id, item.source_uri, item.target_uri))

def _existing_literal_pairs(description: dict[str, Any]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for value in description.get("labels", []):
        pairs.add(("label", value))
    for value in description.get("identifiers", []):
        pairs.add(("identificador", value))
    for value in description.get("text_extracts", []):
        pairs.add(("textoExtracto", value))
    for value in description.get("values", []):
        pairs.add(("valor", value))
    return pairs


def _bridge_allowed(source_desc: dict[str, Any], target_desc: dict[str, Any] | None) -> bool:
    return bool(target_desc and (_same_theme(source_desc, target_desc) or set(source_desc.get("types", [])) & set(target_desc.get("types", []) or []) or _is_reference_like(source_desc) or _is_reference_like(target_desc)))


def _best_structured_value(description: dict[str, Any], expected_answer: str, related_desc: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
    candidates: list[tuple[str, str]] = []
    for value in description.get("identifiers", []) + description.get("values", []):
        for structured in extract_structured_values(value):
            candidates.append((structured, "existing_literal"))
    for text in description.get("text_extracts", []):
        for structured in extract_structured_values(text):
            candidates.append((structured, "text_extract_pattern"))
    if related_desc and _bridge_allowed(description, related_desc):
        for value in related_desc.get("identifiers", []) + related_desc.get("values", []):
            for structured in extract_structured_values(value):
                candidates.append((structured, "related_entity_bridge"))
        for text in related_desc.get("text_extracts", []):
            for structured in extract_structured_values(text):
                candidates.append((structured, "related_entity_bridge"))
    best_value, best_reason, best_score = None, None, -1.0
    for value, reason in candidates:
        score = _preferred_surface_score(value, expected_answer) - (0.05 if reason == "related_entity_bridge" else 0.0)
        if score > best_score:
            best_value, best_reason, best_score = value, reason, score
    return best_value, best_reason


def _best_short_extract(description: dict[str, Any], expected_answer: str, related_desc: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
    def _extract_describes_entity(value: str, entity_description: dict[str, Any]) -> bool:
        entity_tokens = _significant_tokens(
            entity_description.get("local_name", ""),
            *entity_description.get("labels", []),
            *entity_description.get("identifiers", []),
        )
        extract_tokens = _significant_tokens(value)
        if not extract_tokens:
            return False
        return bool(entity_tokens & extract_tokens) and len(value) <= 220

    candidates: list[tuple[str, str]] = []
    for text in description.get("text_extracts", []):
        for fragment in split_text_fragments(text):
            if _extract_describes_entity(fragment, description):
                candidates.append((fragment, "existing_extract_fragment"))
    if related_desc and _bridge_allowed(description, related_desc):
        best_related, _ = best_surface_literal(related_desc, expected_answer)
        if best_related and 8 <= len(best_related) <= 160 and _extract_describes_entity(best_related, description):
            candidates.append((best_related, "related_entity_bridge"))
        for text in related_desc.get("text_extracts", []):
            for fragment in split_text_fragments(text):
                if _extract_describes_entity(fragment, description):
                    candidates.append((fragment, "related_entity_bridge"))
    best_value, best_reason, best_score = None, None, -1.0
    for value, reason in candidates:
        score = _preferred_surface_score(value, expected_answer) - (0.05 if reason == "related_entity_bridge" else 0.0)
        if score > best_score:
            best_value, best_reason, best_score = value, reason, score
    return (best_value, best_reason) if best_score >= 0.55 else (None, None)


def _best_label(description: dict[str, Any]) -> tuple[str | None, str | None]:
    if description.get("labels"):
        return None, None
    local_norm = normalize_text(description.get("local_name", ""))
    humanized = humanize_local_name(description.get("local_name", ""))
    for candidate in description.get("identifiers", []) + description.get("values", []):
        candidate_norm = normalize_text(candidate)
        token_count = len(candidate_norm.split())
        if candidate_norm == local_norm:
            continue
        if token_count < 2 and not extract_structured_values(candidate):
            continue
        if 4 <= len(candidate) <= 80 and not re.search(r"@", candidate):
            return candidate, "label_from_existing_literal"
    return (humanized, "label_from_local_name") if humanized else (None, None)


def detect_surface_enrichments(graph: Graph, corpus: list[EnrichmentCandidate], links: list[LinkEnrichment] | None = None) -> list[SurfaceEnrichment]:
    link_neighbors: dict[str, list[str]] = {}
    for link in links or []:
        link_neighbors.setdefault(link.source_uri, []).append(link.target_uri)
        link_neighbors.setdefault(link.target_uri, []).append(link.source_uri)
    entity_support: dict[str, list[EnrichmentCandidate]] = {}
    for candidate in corpus:
        entity_support.setdefault(candidate.chosen_entity_uri, []).append(candidate)
        if candidate.target_uri:
            entity_support.setdefault(candidate.target_uri, []).append(candidate)
    aggregated: dict[tuple[str, str, str], SurfaceEnrichment] = {}
    for entity_uri, supporting in entity_support.items():
        description = describe_entity(graph, entity_uri)
        existing = _existing_literal_pairs(description)
        related_desc = None
        if link_neighbors.get(entity_uri):
            related_desc = describe_entity(graph, link_neighbors[entity_uri][0])
        elif supporting[0].target_uri and supporting[0].target_uri != entity_uri:
            related_desc = describe_entity(graph, supporting[0].target_uri)
        expected_answer = supporting[0].expected_answer_text
        label_value, label_reason = _best_label(description)
        if label_value and ("label", label_value) not in existing:
            aggregated[(entity_uri, str(RDFS.label), label_value)] = SurfaceEnrichment(entity_uri, str(RDFS.label), label_value, "human_label", label_reason or "label_rule", sorted({item.question_id for item in supporting}), {"entity_types": description.get("types", [])})
        structured_value, structured_reason = _best_structured_value(description, expected_answer, related_desc)
        if structured_value and ("valor", structured_value) not in existing:
            aggregated[(entity_uri, str(EX.valor), structured_value)] = SurfaceEnrichment(entity_uri, str(EX.valor), structured_value, "structured_value", structured_reason or "structured_value_rule", sorted({item.question_id for item in supporting}), {"entity_types": description.get("types", [])})
        if structured_value and not description.get("identifiers") and not re.search(r"@", structured_value) and ("identificador", structured_value) not in existing:
            aggregated[(entity_uri, str(EX.identificador), structured_value)] = SurfaceEnrichment(entity_uri, str(EX.identificador), structured_value, "structured_identifier", structured_reason or "identifier_rule", sorted({item.question_id for item in supporting}), {"entity_types": description.get("types", [])})
        short_extract, extract_reason = _best_short_extract(description, expected_answer, related_desc)
        if short_extract and ("textoExtracto", short_extract) not in existing:
            aggregated[(entity_uri, str(EX.textoExtracto), short_extract)] = SurfaceEnrichment(entity_uri, str(EX.textoExtracto), short_extract, "short_text_extract", extract_reason or "short_extract_rule", sorted({item.question_id for item in supporting}), {"entity_types": description.get("types", [])})
    return sorted(aggregated.values(), key=lambda item: (item.entity_uri, item.added_property_uri, item.added_value))


def candidates_to_jsonable(candidates: list[EnrichmentCandidate]) -> list[dict[str, Any]]:
    return [asdict(candidate) for candidate in candidates]


def links_to_jsonable(links: list[LinkEnrichment]) -> list[dict[str, Any]]:
    return [asdict(link) for link in links]


def surfaces_to_jsonable(surfaces: list[SurfaceEnrichment]) -> list[dict[str, Any]]:
    return [asdict(surface) for surface in surfaces]


def build_enrichment_eval_report(baseline_summary: dict[str, Any], current_summary: dict[str, Any], baseline_promotable_ids: list[str], current_promotable_ids: list[str], qa_canonical_summary: dict[str, Any], qa_multihop_summary: dict[str, Any]) -> dict[str, Any]:
    baseline_counts = Counter(baseline_summary.get("structural_gap_counts", {}))
    current_counts = Counter(current_summary.get("structural_gap_counts", {}))
    focus = ["graph_linking_gap", "missing_value_surface", "synthesis_surface_gap"]
    return {
        "summary": {
            "baseline_structural_gap_counts": dict(baseline_counts),
            "current_structural_gap_counts": dict(current_counts),
            "focus_category_delta": {category: current_counts.get(category, 0) - baseline_counts.get(category, 0) for category in focus},
            "baseline_promotable_count": len(baseline_promotable_ids),
            "current_promotable_count": len(current_promotable_ids),
            "qa_canonical": qa_canonical_summary,
            "qa_multihop": qa_multihop_summary,
        }
    }
