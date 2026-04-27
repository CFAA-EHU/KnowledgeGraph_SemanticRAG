from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS, OWL

from artifact_contracts import OPERATIONAL_TBOX_PATH

PREFERRED_SURFACE_PREDICATES = ('identificador', 'label', 'textoExtracto', 'valor')
SUPPORTED_ISSUES = {'graph_canonicalization_gap', 'graph_linking_gap', 'missing_value_surface'}
ISSUE_PRIORITY = {'graph_canonicalization_gap': 1, 'graph_linking_gap': 2, 'missing_value_surface': 3}
SURFACE_VARIANT_CONTEXT_BLOCKERS = {
    'version',
    'v',
    'seccion',
    'section',
    'canal',
    'channel',
    'cabezal',
    'head',
    'indice',
    'index',
    'pagina',
    'page',
    'capitulo',
    'chapter',
}
SURFACE_VARIANT_MIN_KEY_LENGTH = 5
MANUALLY_CONFLICTING_PAIRS: set[frozenset[str]] = {
    frozenset({"Maquina", "Directiva"}),
    frozenset({"Maquina", "Manual"}),
    frozenset({"Maquina", "PiezaRecambio"}),
    frozenset({"Empresa", "Directiva"}),
    frozenset({"TareaMantenimiento", "ComponenteElectrico"}),
    frozenset({"Alarma", "PlanMantenimiento"}),
    frozenset({"CodigoError", "Figura"}),
}
_TBOX_SUBCLASS_CLOSURE: dict[str, set[str]] | None = None
_TBOX_DISJOINT_PAIRS: set[frozenset[str]] | None = None


@dataclass
class ResolutionCandidate:
    source_uri: str
    candidate_uri: str
    entity_type: str
    suggested_structural_issue: str
    priority: int
    support_count: int
    question_ids: list[str] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)
    candidate_types: list[str] = field(default_factory=list)
    source_best_surface_literal: str | None = None
    candidate_best_surface_literal: str | None = None
    source_alignment_score: float = 0.0
    candidate_alignment_score: float = 0.0
    improvement_score: float = 0.0
    reason: str | None = None
    candidate_origin: str = 'sandbox'
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolutionCluster:
    source_uri: str
    entity_type: str
    source_types: list[str]
    source_best_surface_literal: str | None
    candidates: list[ResolutionCandidate] = field(default_factory=list)


@dataclass
class CanonicalSelection:
    source_uri: str
    canonical_uri: str
    absorbed_uris: list[str]
    supplemental_targets: list[str]
    entity_type: str
    resolution_reason: str
    rules_applied: list[str]
    selection_scores: dict[str, float]
    support_question_ids: list[str]


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize('NFKD', text or '')
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r'[^a-z0-9@/_\-.]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def normalize_uri(uri: str) -> str:
    return str(uri).split('/')[-1].split('#')[-1]


def _load_tbox_subclass_closure() -> dict[str, set[str]]:
    global _TBOX_SUBCLASS_CLOSURE
    if _TBOX_SUBCLASS_CLOSURE is not None:
        return _TBOX_SUBCLASS_CLOSURE

    graph = Graph()
    graph.parse(OPERATIONAL_TBOX_PATH, format='turtle')
    parents: dict[str, set[str]] = {}
    for child, _, parent in graph.triples((None, RDFS.subClassOf, None)):
        if isinstance(child, URIRef) and isinstance(parent, URIRef):
            parents.setdefault(normalize_uri(str(child)), set()).add(normalize_uri(str(parent)))

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
    _TBOX_SUBCLASS_CLOSURE = closure
    return closure


def _load_tbox_disjoint_pairs() -> set[frozenset[str]]:
    global _TBOX_DISJOINT_PAIRS
    if _TBOX_DISJOINT_PAIRS is not None:
        return _TBOX_DISJOINT_PAIRS

    graph = Graph()
    graph.parse(OPERATIONAL_TBOX_PATH, format='turtle')
    pairs: set[frozenset[str]] = set()
    for left, _, right in graph.triples((None, OWL.disjointWith, None)):
        if isinstance(left, URIRef) and isinstance(right, URIRef):
            pairs.add(frozenset({normalize_uri(str(left)), normalize_uri(str(right))}))
    _TBOX_DISJOINT_PAIRS = pairs
    return pairs


def extract_key_literals(text: str) -> list[str]:
    text = text or ''
    patterns = [
        r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}',
        r'\b\d{4}/\d{2}/[A-Z]{2}\b',
        r'\bfigura\s*\d+(?:[-.]\d+)+\b',
        r'\b[A-Z]{1,4}-?\d{1,6}\b',
        r'\bSQ\d+\b',
        r'\b\d+(?:[.,]\d+)?\s*(?:mm|m/min|kn|bar|v|a|kg|hz|nlg[iI]?\s*[0-9-]+|nlg[iI])\b',
    ]
    values: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text, re.I):
            normalized = normalize_text(match)
            if normalized and normalized not in values:
                values.append(normalized)
    return values


def _token_overlap(a: str, b: str) -> float:
    a_tokens = {token for token in normalize_text(a).split() if len(token) >= 3}
    b_tokens = {token for token in normalize_text(b).split() if len(token) >= 3}
    if not a_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(len(a_tokens), 1)


def _string_similarity(a: str, b: str) -> float:
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def _structured_identifier_score(value: str | None) -> float:
    if not value:
        return 0.0
    value_norm = value.strip()
    if re.search(r'\d{4}/\d{2}/[A-Z]{2}', value_norm, re.I):
        return 1.0
    if re.search(r'[A-Z]{1,6}-?\d{1,6}', value_norm):
        return 0.85
    if re.search(r'\d', value_norm) and ('-' in value_norm or '/' in value_norm):
        return 0.75
    if len(value_norm) <= 24 and re.search(r'\d', value_norm):
        return 0.55
    return 0.0


def _identifier_heavy_penalty(value: str) -> float:
    local = normalize_uri(value)
    if re.search(r'[A-Z][a-z]+[A-Z][A-Za-z0-9]+', local):
        return 0.35
    if '_' in local or re.search(r'\d', local):
        return 0.2
    return 0.0


def _load_json(payload_or_path: Any) -> Any:
    if isinstance(payload_or_path, (str, Path)):
        path = Path(payload_or_path)
        return json.loads(path.read_text(encoding='utf-8'))
    return payload_or_path


def _normalize_surface_variant_text(text: str) -> str:
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', text)
    text = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', text)
    text = text.replace('_', ' ').replace('-', ' ')
    text = re.sub(r'[^A-Za-z0-9 ]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text


def _compact_surface_variant_key(text: str) -> str:
    normalized = _normalize_surface_variant_text(text)
    return normalized.replace(' ', '')


def _surface_variant_tokens(text: str) -> list[str]:
    return [token for token in _normalize_surface_variant_text(text).split() if token]


def _has_contextual_surface_blockers(*values: str) -> bool:
    tokens: set[str] = set()
    for value in values:
        tokens.update(_surface_variant_tokens(value))
    if any(token in SURFACE_VARIANT_CONTEXT_BLOCKERS for token in tokens):
        return True
    if any(re.fullmatch(r'v\d+(?:\.\d+)*', token) for token in tokens):
        return True
    if any(re.fullmatch(r'\d+', token) for token in tokens):
        return True
    return False


def describe_entity(graph: Graph, uri: str) -> dict[str, Any]:
    subject = URIRef(uri)
    surface_literals: list[dict[str, str]] = []
    outgoing_predicates: list[str] = []
    types: list[str] = []
    for _, predicate, obj in graph.triples((subject, None, None)):
        predicate_local = normalize_uri(predicate)
        outgoing_predicates.append(predicate_local)
        if predicate == RDF.type and isinstance(obj, URIRef):
            types.append(str(obj))
        if predicate_local in PREFERRED_SURFACE_PREDICATES and not isinstance(obj, URIRef):
            surface_literals.append({'predicate': predicate_local, 'value': str(obj)})
    incoming_count = sum(1 for _ in graph.subject_predicates(subject))
    preferred_identifier = next((item['value'] for item in surface_literals if item['predicate'] == 'identificador'), None)
    preferred_label = next((item['value'] for item in surface_literals if item['predicate'] == 'label'), None)
    best_surface = preferred_identifier or preferred_label or (surface_literals[0]['value'] if surface_literals else normalize_uri(uri))
    return {
        'uri': uri,
        'local_name': normalize_uri(uri),
        'types': [normalize_uri(item) for item in types],
        'incoming_count': incoming_count,
        'surface_literals': surface_literals,
        'outgoing_predicates': outgoing_predicates,
        'best_surface': best_surface,
        'preferred_identifier': preferred_identifier,
        'preferred_label': preferred_label,
    }


def _surface_variant_key_matches(source_desc: dict[str, Any], candidate_desc: dict[str, Any]) -> tuple[bool, list[str]]:
    source_values = [
        source_desc.get('preferred_label') or '',
        source_desc.get('preferred_identifier') or '',
        source_desc.get('best_surface') or '',
        source_desc.get('local_name') or '',
    ]
    candidate_values = [
        candidate_desc.get('preferred_label') or '',
        candidate_desc.get('preferred_identifier') or '',
        candidate_desc.get('best_surface') or '',
        candidate_desc.get('local_name') or '',
    ]
    source_keys = {_compact_surface_variant_key(value) for value in source_values if value}
    candidate_keys = {_compact_surface_variant_key(value) for value in candidate_values if value}
    source_keys = {key for key in source_keys if len(key) >= SURFACE_VARIANT_MIN_KEY_LENGTH}
    candidate_keys = {key for key in candidate_keys if len(key) >= SURFACE_VARIANT_MIN_KEY_LENGTH}
    shared = sorted(source_keys & candidate_keys)
    return bool(shared), shared


def _surface_variant_pair_acceptable(source_desc: dict[str, Any], candidate_desc: dict[str, Any]) -> tuple[bool, str, list[str]]:
    compatible = _types_compatible(source_desc['types'], candidate_desc['types'])
    if not compatible:
        return False, 'incompatible_entity_types', []
    shared, shared_keys = _surface_variant_key_matches(source_desc, candidate_desc)
    if not shared:
        return False, 'surface_variant_key_mismatch', []
    best_surface_similarity = max(
        _string_similarity(source_desc.get('best_surface') or '', candidate_desc.get('best_surface') or ''),
        _string_similarity(source_desc.get('preferred_label') or '', candidate_desc.get('preferred_label') or ''),
        _string_similarity(source_desc.get('local_name') or '', candidate_desc.get('local_name') or ''),
    )
    if best_surface_similarity < 0.92:
        return False, 'surface_similarity_below_threshold', shared_keys
    if _has_contextual_surface_blockers(source_desc.get('local_name') or '', candidate_desc.get('local_name') or ''):
        return False, 'contextual_suffix_blocked', shared_keys
    return True, 'surface_variant_canonicalization', shared_keys


def _best_surface_against_expected(description: dict[str, Any], expected_answer: str) -> tuple[str | None, float]:
    expected_norm = normalize_text(expected_answer)
    expected_keys = set(extract_key_literals(expected_answer))
    best_value = description.get('best_surface')
    best_score = 0.0
    candidates = [literal['value'] for literal in description.get('surface_literals', [])] or [description.get('best_surface') or '']
    for value in candidates:
        overlap = _token_overlap(expected_answer, value)
        similarity = _string_similarity(expected_norm, value)
        literal_hits = len(expected_keys & set(extract_key_literals(value)))
        score = overlap + similarity + (literal_hits * 0.4) + _structured_identifier_score(value)
        if score > best_score:
            best_score = score
            best_value = value
    return best_value, round(best_score, 4)


def _types_compatible(source_types: list[str], candidate_types: list[str]) -> bool:
    if not source_types or not candidate_types:
        return False
    source_set = set(source_types)
    candidate_set = set(candidate_types)
    if source_set & candidate_set:
        return True

    subclass_closure = _load_tbox_subclass_closure()
    disjoint_pairs = _load_tbox_disjoint_pairs()
    for source_type in source_set:
        for candidate_type in candidate_set:
            pair = frozenset({source_type, candidate_type})
            if pair in disjoint_pairs:
                return False
            if candidate_type in subclass_closure.get(source_type, set()):
                return True
            if source_type in subclass_closure.get(candidate_type, set()):
                return True
            if pair in MANUALLY_CONFLICTING_PAIRS:
                return False
    return False


def _pair_signals(graph: Graph, source_uri: str, candidate_uri: str, expected_answer: str) -> dict[str, Any]:
    source_desc = describe_entity(graph, source_uri)
    candidate_desc = describe_entity(graph, candidate_uri)
    source_surface, source_alignment = _best_surface_against_expected(source_desc, expected_answer)
    candidate_surface, candidate_alignment = _best_surface_against_expected(candidate_desc, expected_answer)
    expected_keys = set(extract_key_literals(expected_answer))
    source_keys = set(extract_key_literals(source_surface or '')) | set(extract_key_literals(source_desc.get('preferred_identifier') or ''))
    candidate_keys = set(extract_key_literals(candidate_surface or '')) | set(extract_key_literals(candidate_desc.get('preferred_identifier') or ''))
    pair_surface_similarity = max(
        _string_similarity(source_desc.get('best_surface') or '', candidate_desc.get('best_surface') or ''),
        _string_similarity(source_desc.get('preferred_identifier') or '', candidate_desc.get('preferred_identifier') or ''),
        _token_overlap(source_desc.get('best_surface') or '', candidate_desc.get('best_surface') or ''),
    )
    return {
        'source_desc': source_desc,
        'candidate_desc': candidate_desc,
        'source_surface': source_surface,
        'candidate_surface': candidate_surface,
        'source_alignment': source_alignment,
        'candidate_alignment': candidate_alignment,
        'improvement': round(candidate_alignment - source_alignment, 4),
        'source_structured_identifier': _structured_identifier_score(source_desc.get('preferred_identifier')),
        'candidate_structured_identifier': _structured_identifier_score(candidate_desc.get('preferred_identifier')),
        'expected_key_literals': sorted(expected_keys),
        'source_key_hits': len(expected_keys & source_keys),
        'candidate_key_hits': len(expected_keys & candidate_keys),
        'pair_surface_similarity': round(pair_surface_similarity, 4),
        'types_compatible': _types_compatible(source_desc['types'], candidate_desc['types']),
    }


def _should_keep_candidate(issue: str, signals: dict[str, Any]) -> tuple[bool, str]:
    if not signals['types_compatible']:
        return False, 'incompatible_entity_types'
    if issue == 'graph_canonicalization_gap':
        if signals['candidate_key_hits'] > signals['source_key_hits'] and signals['candidate_structured_identifier'] >= 0.75:
            return True, 'expected_reference_key_literal_preferred'
        if signals['candidate_alignment'] >= 1.05 and signals['improvement'] >= 0.25:
            return True, 'strong_expected_alignment_improvement'
        return False, 'insufficient_canonical_alignment_gain'
    if issue == 'graph_linking_gap':
        if signals['candidate_alignment'] >= 0.9 and signals['candidate_key_hits'] >= signals['source_key_hits']:
            return True, 'linkable_candidate_with_expected_alignment'
        return False, 'insufficient_linking_alignment_gain'
    if issue == 'missing_value_surface':
        if signals['candidate_alignment'] >= 0.72 and signals['improvement'] >= 0.12:
            return True, 'better_surface_literal_available'
        return False, 'surface_gain_too_small'
    return False, 'unsupported_issue'


def collect_resolution_diagnostics(
    graph: Graph,
    sandbox_candidates: Any,
    sandbox_summary: Any,
    sandbox_decision: Any,
    sandbox_report: Any | None = None,
) -> dict[str, Any]:
    sandbox_candidates = _load_json(sandbox_candidates)
    sandbox_summary = _load_json(sandbox_summary)
    sandbox_decision = _load_json(sandbox_decision)
    sandbox_report = _load_json(sandbox_report) if sandbox_report is not None else {'results': []}
    report_by_question = {item['question_id']: item for item in sandbox_report.get('results', [])}
    aggregated: dict[tuple[str, str, str], ResolutionCandidate] = {}
    discarded: list[dict[str, Any]] = []

    for entry in sandbox_candidates.get('results', []):
        question_id = entry.get('question_id')
        report_item = report_by_question.get(question_id, {})
        issue = entry.get('suggested_structural_issue') or report_item.get('structural_gap_category')
        if issue not in SUPPORTED_ISSUES:
            discarded.append({'question_id': question_id, 'source_uri': entry.get('chosen_entity_uri'), 'candidate_uri': None, 'reason': 'unsupported_issue'})
            continue
        expected_answer = report_item.get('expected_answer_text') or report_item.get('answer') or ''
        source_uri = entry.get('chosen_entity_uri')
        if not source_uri or not expected_answer:
            discarded.append({'question_id': question_id, 'source_uri': source_uri, 'candidate_uri': None, 'reason': 'missing_source_or_expected_answer'})
            continue
        for candidate in entry.get('candidate_entities', []):
            candidate_uri = candidate.get('uri')
            if not candidate_uri:
                discarded.append({'question_id': question_id, 'source_uri': source_uri, 'candidate_uri': None, 'reason': 'missing_candidate_uri'})
                continue
            signals = _pair_signals(graph, source_uri, candidate_uri, expected_answer)
            keep, reason = _should_keep_candidate(issue, signals)
            if not keep:
                discarded.append({'question_id': question_id, 'source_uri': source_uri, 'candidate_uri': candidate_uri, 'reason': reason, 'issue': issue})
                continue
            key = (source_uri, candidate_uri, issue)
            priority = ISSUE_PRIORITY[issue]
            candidate_entry = aggregated.get(key)
            if candidate_entry is None:
                candidate_entry = ResolutionCandidate(
                    source_uri=source_uri,
                    candidate_uri=candidate_uri,
                    entity_type=(signals['source_desc']['types'][0] if signals['source_desc']['types'] else 'Unknown'),
                    suggested_structural_issue=issue,
                    priority=priority,
                    support_count=0,
                    question_ids=[],
                    source_types=signals['source_desc']['types'],
                    candidate_types=signals['candidate_desc']['types'],
                    source_best_surface_literal=signals['source_surface'],
                    candidate_best_surface_literal=signals['candidate_surface'],
                    source_alignment_score=signals['source_alignment'],
                    candidate_alignment_score=signals['candidate_alignment'],
                    improvement_score=signals['improvement'],
                    reason=reason,
                    candidate_origin='sandbox',
                    evidence={
                        'source_key_hits': signals['source_key_hits'],
                        'candidate_key_hits': signals['candidate_key_hits'],
                        'pair_surface_similarity': signals['pair_surface_similarity'],
                        'source_structured_identifier': signals['source_structured_identifier'],
                        'candidate_structured_identifier': signals['candidate_structured_identifier'],
                    },
                )
                aggregated[key] = candidate_entry
            if question_id not in candidate_entry.question_ids:
                candidate_entry.question_ids.append(question_id)
                candidate_entry.support_count += 1
            candidate_entry.candidate_alignment_score = max(candidate_entry.candidate_alignment_score, signals['candidate_alignment'])
            candidate_entry.source_alignment_score = max(candidate_entry.source_alignment_score, signals['source_alignment'])
            candidate_entry.improvement_score = max(candidate_entry.improvement_score, signals['improvement'])

    accepted = sorted(
        aggregated.values(),
        key=lambda item: (item.priority, -item.support_count, -item.improvement_score, -item.candidate_alignment_score, item.source_uri, item.candidate_uri),
    )
    return {
        'accepted': accepted,
        'discarded': discarded,
        'summary': {
            'dominant_structural_gap_category': sandbox_decision.get('dominant_structural_gap_category'),
            'structural_gap_counts': sandbox_summary.get('summary', {}).get('structural_gap_counts', {}),
            'accepted_candidates': len(accepted),
            'discarded_candidates': len(discarded),
            'candidate_origins': {'sandbox': len(accepted)},
        },
    }


def collect_surface_variant_diagnostics(graph: Graph) -> dict[str, Any]:
    descriptions: dict[str, dict[str, Any]] = {}
    for subject, _, obj in graph.triples((None, RDF.type, None)):
        if not isinstance(subject, URIRef) or not isinstance(obj, URIRef):
            continue
        uri = str(subject)
        if uri not in descriptions:
            descriptions[uri] = describe_entity(graph, uri)

    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for uri, description in descriptions.items():
        candidate_values = {
            description.get('preferred_label') or '',
            description.get('preferred_identifier') or '',
            description.get('best_surface') or '',
            description.get('local_name') or '',
        }
        for value in candidate_values:
            key = _compact_surface_variant_key(value)
            if len(key) < SURFACE_VARIANT_MIN_KEY_LENGTH:
                continue
            grouped[key][uri] = description

    accepted: list[ResolutionCandidate] = []
    discarded: list[dict[str, Any]] = []
    inspected_groups = 0

    for key, members in grouped.items():
        if len(members) < 2:
            continue
        inspected_groups += 1
        ordered_members = sorted(
            members.values(),
            key=lambda item: (-item.get('incoming_count', 0), -len(item.get('surface_literals', [])), item.get('local_name', '')),
        )
        source_desc = ordered_members[0]
        accepted_for_group = 0
        for candidate_desc in ordered_members[1:]:
            keep, reason, shared_keys = _surface_variant_pair_acceptable(source_desc, candidate_desc)
            if not keep:
                discarded.append(
                    {
                        'source_uri': source_desc['uri'],
                        'candidate_uri': candidate_desc['uri'],
                        'reason': reason,
                        'issue': 'graph_canonicalization_gap',
                        'candidate_origin': 'surface_variant_scan',
                        'shared_surface_variant_keys': shared_keys,
                    }
                )
                continue
            pair_similarity = max(
                _string_similarity(source_desc.get('best_surface') or '', candidate_desc.get('best_surface') or ''),
                _string_similarity(source_desc.get('preferred_label') or '', candidate_desc.get('preferred_label') or ''),
                _string_similarity(source_desc.get('local_name') or '', candidate_desc.get('local_name') or ''),
            )
            accepted.append(
                ResolutionCandidate(
                    source_uri=source_desc['uri'],
                    candidate_uri=candidate_desc['uri'],
                    entity_type=(source_desc['types'][0] if source_desc['types'] else 'Unknown'),
                    suggested_structural_issue='graph_canonicalization_gap',
                    priority=ISSUE_PRIORITY['graph_canonicalization_gap'],
                    support_count=1,
                    question_ids=[],
                    source_types=source_desc['types'],
                    candidate_types=candidate_desc['types'],
                    source_best_surface_literal=source_desc.get('best_surface'),
                    candidate_best_surface_literal=candidate_desc.get('best_surface'),
                    source_alignment_score=round(pair_similarity, 4),
                    candidate_alignment_score=round(pair_similarity, 4),
                    improvement_score=round(pair_similarity, 4),
                    reason=reason,
                    candidate_origin='surface_variant_scan',
                    evidence={
                        'pair_surface_similarity': round(pair_similarity, 4),
                        'shared_surface_variant_keys': shared_keys,
                        'source_local_name': source_desc.get('local_name'),
                        'candidate_local_name': candidate_desc.get('local_name'),
                        'source_incoming_count': source_desc.get('incoming_count', 0),
                        'candidate_incoming_count': candidate_desc.get('incoming_count', 0),
                    },
                )
            )
            accepted_for_group += 1
        if accepted_for_group == 0:
            discarded.append(
                {
                    'source_uri': source_desc['uri'],
                    'candidate_uri': None,
                    'reason': 'no_safe_surface_variant_candidates',
                    'issue': 'graph_canonicalization_gap',
                    'candidate_origin': 'surface_variant_scan',
                    'shared_surface_variant_keys': [key],
                }
            )

    return {
        'accepted': accepted,
        'discarded': discarded,
        'summary': {
            'surface_variant_groups_inspected': inspected_groups,
            'accepted_candidates': len(accepted),
            'discarded_candidates': len(discarded),
            'candidate_origins': {'surface_variant_scan': len(accepted)},
        },
    }


def build_resolution_corpus(
    graph: Graph,
    sandbox_candidates: Any,
    sandbox_summary: Any,
    sandbox_decision: Any,
    sandbox_report: Any | None = None,
) -> list[ResolutionCandidate]:
    return collect_resolution_diagnostics(graph, sandbox_candidates, sandbox_summary, sandbox_decision, sandbox_report)['accepted']


def group_resolution_candidates(candidates: list[ResolutionCandidate]) -> list[ResolutionCluster]:
    grouped: dict[str, list[ResolutionCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.source_uri].append(candidate)
    clusters: list[ResolutionCluster] = []
    for source_uri, cluster_candidates in grouped.items():
        cluster_candidates.sort(key=lambda item: (item.priority, -item.support_count, -item.candidate_alignment_score, -item.improvement_score, item.candidate_uri))
        types = cluster_candidates[0].source_types
        entity_type = cluster_candidates[0].entity_type
        source_best_surface_literal = cluster_candidates[0].source_best_surface_literal
        clusters.append(
            ResolutionCluster(
                source_uri=source_uri,
                entity_type=entity_type,
                source_types=types,
                source_best_surface_literal=source_best_surface_literal,
                candidates=cluster_candidates,
            )
        )
    clusters.sort(key=lambda cluster: (cluster.candidates[0].priority, -len(cluster.candidates), cluster.source_uri))
    return clusters


def _node_selection_score(graph: Graph, uri: str, cluster: ResolutionCluster) -> tuple[float, dict[str, float], dict[str, Any]]:
    description = describe_entity(graph, uri)
    structured_identifier = _structured_identifier_score(description.get('preferred_identifier'))
    human_surface = 0.8 if description.get('preferred_label') else 0.0
    if description.get('preferred_identifier') and structured_identifier >= 0.55:
        human_surface += 0.7
    incoming_score = min(description.get('incoming_count', 0), 6) * 0.18
    coverage_score = min(len(description.get('surface_literals', [])), 6) * 0.08 + min(len(description.get('outgoing_predicates', [])), 12) * 0.03
    support_score = sum(candidate.support_count for candidate in cluster.candidates if candidate.candidate_uri == uri) * 0.5
    source_penalty = 0.15 if uri == cluster.source_uri else 0.0
    identifier_penalty = _identifier_heavy_penalty(description.get('local_name', ''))
    total = structured_identifier * 2.6 + human_surface + incoming_score + coverage_score + support_score - source_penalty - identifier_penalty
    return round(total, 4), {
        'structured_identifier': round(structured_identifier, 4),
        'human_surface': round(human_surface, 4),
        'incoming_score': round(incoming_score, 4),
        'coverage_score': round(coverage_score, 4),
        'support_score': round(support_score, 4),
        'source_penalty': round(source_penalty, 4),
        'identifier_penalty': round(identifier_penalty, 4),
    }, description


def select_canonical_entity(cluster: ResolutionCluster, graph: Graph) -> CanonicalSelection:
    candidate_uris = [cluster.source_uri] + [candidate.candidate_uri for candidate in cluster.candidates]
    unique_uris = list(dict.fromkeys(candidate_uris))
    scores: dict[str, float] = {}
    descriptions: dict[str, dict[str, Any]] = {}
    applied_rules = ['shared_type_gate', 'structured_identifier_preference', 'human_surface_preference', 'incoming_links_preference', 'factual_coverage_preference']
    for uri in unique_uris:
        total, components, description = _node_selection_score(graph, uri, cluster)
        scores[uri] = total
        descriptions[uri] = {'components': components, 'description': description}
    canonical_uri = sorted(unique_uris, key=lambda uri: (-scores[uri], uri))[0]
    canonical_description = descriptions[canonical_uri]['description']
    absorbed_uris = [cluster.source_uri] if canonical_uri != cluster.source_uri else []
    supplemental_targets: list[str] = []
    canonical_codes = set(extract_key_literals(canonical_description.get('preferred_identifier') or canonical_description.get('best_surface') or ''))
    for candidate in cluster.candidates:
        if candidate.candidate_uri == canonical_uri:
            continue
        candidate_codes = set(extract_key_literals(candidate.candidate_best_surface_literal or ''))
        if candidate.support_count < 1:
            continue
        if candidate.candidate_alignment_score < 1.0 or candidate.improvement_score < 0.25:
            continue
        if canonical_codes and candidate_codes and canonical_codes == candidate_codes:
            continue
        supplemental_targets.append(candidate.candidate_uri)
    supplemental_targets = list(dict.fromkeys(supplemental_targets))[:3]
    reason = 'higher_surface_quality_and_support'
    if descriptions[canonical_uri]['components']['structured_identifier'] > 0.7:
        reason = 'structured_identifier_preferred'
    if canonical_uri == cluster.source_uri and supplemental_targets:
        reason = 'source_preserved_with_supplemental_targets'
    support_question_ids = sorted({question_id for candidate in cluster.candidates for question_id in candidate.question_ids})
    return CanonicalSelection(
        source_uri=cluster.source_uri,
        canonical_uri=canonical_uri,
        absorbed_uris=absorbed_uris,
        supplemental_targets=supplemental_targets,
        entity_type=cluster.entity_type,
        resolution_reason=reason,
        rules_applied=applied_rules,
        selection_scores={uri: scores[uri] for uri in unique_uris},
        support_question_ids=support_question_ids,
    )


def candidates_to_jsonable(candidates: list[ResolutionCandidate]) -> list[dict[str, Any]]:
    return [asdict(candidate) for candidate in candidates]


def clusters_to_jsonable(clusters: list[ResolutionCluster]) -> list[dict[str, Any]]:
    return [asdict(cluster) for cluster in clusters]


def selections_to_jsonable(selections: list[CanonicalSelection]) -> list[dict[str, Any]]:
    return [asdict(selection) for selection in selections]
