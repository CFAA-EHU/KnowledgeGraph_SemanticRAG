import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict
from difflib import SequenceMatcher
from statistics import mean
from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from artifact_contracts import (
    BOUNDEDNESS_POLICY_MATRIX_PATH,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
    PLANNER_GENERALIZATION_CATALOG_PATH,
    QA_SANDBOX_PATH,
    SANDBOX_DECISION_REPORT_PATH,
    SANDBOX_DIAGNOSTIC_REPORT_PATH,
    SANDBOX_ENTITY_RESOLUTION_CANDIDATES_PATH,
    SANDBOX_PROMOTION_CANDIDATES_PATH,
    SANDBOX_STRUCTURAL_GAP_SUMMARY_PATH,
    SCHEMA_CONDENSED_PATH,
)

RETRIEVAL_DIR = Path(__file__).resolve().parent
if str(RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(RETRIEVAL_DIR))

from synthesis_pipeline import synthesize_answer
from text_to_sparql import build_query_plan, execute_query_plan, normalize_uri, tokenize_question

NEGATIVE_MARKERS = [
    'no dispongo',
    'no se encuentra',
    'no hay informacion',
    'no se encontraron',
    'context is insufficient',
    '[empty]',
]

SURFACE_LITERAL_PREDICATES = {'label', 'identificador', 'textoExtracto', 'valor'}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run batch structural diagnostics over QA_sandbox using the real runtime pipeline, defaulting to the enriched operational A-Box.')
    parser.add_argument('--qa-file', type=Path, default=QA_SANDBOX_PATH, help='Sandbox QA dataset path.')
    parser.add_argument('--tbox-file', type=Path, default=OPERATIONAL_TBOX_PATH, help='T-Box path to load.')
    parser.add_argument('--abox-file', type=Path, default=OPERATIONAL_ABOX_PATH, help='A-Box path to load.')
    parser.add_argument('--report-path', type=Path, default=SANDBOX_DIAGNOSTIC_REPORT_PATH, help='Detailed per-question report path.')
    parser.add_argument('--summary-path', type=Path, default=SANDBOX_STRUCTURAL_GAP_SUMMARY_PATH, help='Aggregated structural summary path.')
    parser.add_argument('--resolution-candidates-path', type=Path, default=SANDBOX_ENTITY_RESOLUTION_CANDIDATES_PATH, help='Entity resolution candidates path.')
    parser.add_argument('--promotion-path', type=Path, default=SANDBOX_PROMOTION_CANDIDATES_PATH, help='Promotion candidates path.')
    parser.add_argument('--decision-path', type=Path, default=SANDBOX_DECISION_REPORT_PATH, help='Decision report path.')
    parser.add_argument('--limit', type=int, default=0, help='Optional question limit for smoke runs.')
    parser.add_argument('--sleep-seconds', type=float, default=0.0, help='Optional pause between questions.')
    return parser.parse_args()


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize('NFKD', text or '')
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r'[^a-z0-9@/_\-.]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def normalize_answer_text(text: str) -> str:
    return normalize_text(text).replace(' ce ', ' ce ')


def looks_like_identifier(text: str) -> bool:
    if not text:
        return False
    return bool(
        re.search(r'https?://', text)
        or '_' in text
        or re.search(r'[A-Z][a-z]+[A-Z][A-Za-z0-9]+', text)
        or re.fullmatch(r'[A-Za-z]+(?:\d+|_\d+)+(?:_[A-Za-z0-9]+)*', text)
    )


def extract_key_literals(text: str) -> list[str]:
    normalized = text or ''
    patterns = [
        r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}',
        r'\b\d{4}/\d{2}/[A-Z]{2}\b',
        r'\bfigura\s*\d+(?:[-.]\d+)+\b',
        r'\b[A-Z]{1,4}-?\d{1,4}\b',
        r'\bSQ\d+\b',
        r'\b\d+(?:[.,]\d+)?\s*(?:mm|m/min|kn|bar|v|a|kg|nlg[iI]?\s*[0-9-]+|nlg[iI])\b',
    ]
    results: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, normalized, re.I):
            lowered = normalize_text(match)
            if lowered and lowered not in results:
                results.append(lowered)
    return results


def overlap_ratio(expected: str, actual: str) -> float:
    expected_tokens = set(tokenize_question(expected))
    actual_tokens = set(tokenize_question(actual))
    if not expected_tokens:
        return 0.0
    return round(len(expected_tokens & actual_tokens) / max(len(expected_tokens), 1), 4)


def classify_match(expected: str, actual: str) -> tuple[str, bool, float, list[str]]:
    expected_norm = normalize_answer_text(expected)
    actual_norm = normalize_answer_text(actual)
    expected_keys = extract_key_literals(expected)
    actual_keys = extract_key_literals(actual)
    key_hit = bool(set(expected_keys) & set(actual_keys)) if expected_keys else False
    overlap = overlap_ratio(expected, actual)
    seq_ratio = SequenceMatcher(None, expected_norm, actual_norm).ratio() if expected_norm and actual_norm else 0.0
    if expected_norm and actual_norm and expected_norm == actual_norm:
        return 'exact', key_hit, overlap, expected_keys
    if expected_norm and actual_norm and (expected_norm in actual_norm or actual_norm in expected_norm or seq_ratio >= 0.88):
        return 'high_partial', key_hit, overlap, expected_keys
    if overlap >= 0.55 or seq_ratio >= 0.72:
        return 'high_partial', key_hit, overlap, expected_keys
    if overlap >= 0.35 or seq_ratio >= 0.5:
        return 'partial', key_hit, overlap, expected_keys
    if key_hit or overlap >= 0.18 or seq_ratio >= 0.32:
        return 'weak', key_hit, overlap, expected_keys
    return 'none', key_hit, overlap, expected_keys


def classify_surface_quality(expected: str, actual: str, match_mode: str) -> str:
    actual_norm = normalize_answer_text(actual)
    if not actual_norm or any(marker in actual_norm for marker in NEGATIVE_MARKERS):
        return 'underspecified'
    if looks_like_identifier(actual):
        return 'identifier_heavy'
    expected_len = max(len(tokenize_question(expected)), 1)
    actual_len = max(len(tokenize_question(actual)), 1)
    if actual_len > max(expected_len * 2, 20) and match_mode in {'partial', 'weak'}:
        return 'overspecified'
    if match_mode in {'exact', 'high_partial'}:
        return 'clean'
    return 'acceptable'


def rows_for_synthesis(execution) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for row in execution.raw_bindings:
        if len(row) != 3:
            continue
        subject, predicate, obj = row
        subject_value = normalize_uri(subject) if isinstance(subject, str) and subject.startswith('http') else str(subject)
        predicate_value = normalize_uri(predicate) if isinstance(predicate, str) and predicate.startswith('http') else str(predicate)
        obj_value = normalize_uri(obj) if isinstance(obj, str) and obj.startswith('http') else str(obj)
        rows.append((subject_value, predicate_value, obj_value))
    return rows


def load_graph(tbox_path: Path, abox_path: Path) -> Graph:
    graph = Graph()
    graph.parse(tbox_path, format='turtle')
    graph.parse(abox_path, format='turtle')
    return graph


def load_schema() -> str:
    if not SCHEMA_CONDENSED_PATH.exists():
        return ''
    return SCHEMA_CONDENSED_PATH.read_text(encoding='utf-8')


def load_dataset(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    rows: list[dict[str, Any]] = []
    for block_index, block in enumerate(payload):
        group = block.get('group', f'group_{block_index:02d}')
        for question_index, item in enumerate(block.get('questions', [])):
            rows.append(
                {
                    'group': group,
                    'block_index': block_index,
                    'question_index': question_index,
                    'question_id': item['question_id'],
                    'question': item['question'],
                    'answer': item['answer'],
                    'intent': item.get('intent'),
                    'expected_uris': item.get('expected_uris', []),
                    'evaluation_mode': item.get('evaluation_mode'),
                    'source_pages': item.get('source_pages', []),
                    'source_section': item.get('source_section'),
                    'source_note': item.get('source_note'),
                }
            )
    return rows


def build_local_uri_index(graph: Graph) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for subject in graph.subjects():
        if isinstance(subject, URIRef):
            local = normalize_uri(subject)
            index[local].append(str(subject))
    return dict(index)


def extract_uri_map(raw_bindings: list[tuple[str, ...]]) -> dict[str, list[str]]:
    uri_map: dict[str, list[str]] = defaultdict(list)
    for row in raw_bindings:
        for value in row:
            if isinstance(value, str) and value.startswith('http'):
                local = normalize_uri(value)
                if value not in uri_map[local]:
                    uri_map[local].append(value)
    return dict(uri_map)


def choose_entity_uri(result: dict[str, Any], uri_index: dict[str, list[str]]) -> str | None:
    selected = result.get('synthesis_trace', {}).get('selected_evidence', [])
    uri_map = result.get('_uri_map', {})
    for candidate in selected:
        subject_local = candidate.get('subject')
        if not subject_local:
            continue
        if subject_local in uri_map and uri_map[subject_local]:
            return uri_map[subject_local][0]
        if subject_local in uri_index and uri_index[subject_local]:
            return uri_index[subject_local][0]
    for row in result.get('_raw_bindings', []):
        for value in row:
            if isinstance(value, str) and value.startswith('http'):
                return value
    return None


def describe_entity(graph: Graph, uri: str) -> dict[str, Any]:
    subject = URIRef(uri)
    predicates: list[dict[str, Any]] = []
    literals: list[dict[str, str]] = []
    types: list[str] = []
    for _, predicate, obj in graph.triples((subject, None, None)):
        predicate_local = normalize_uri(predicate)
        if predicate == RDF.type and isinstance(obj, URIRef):
            types.append(str(obj))
        obj_value = str(obj)
        entry = {
            'predicate': predicate_local,
            'object': normalize_uri(obj) if isinstance(obj, URIRef) else obj_value,
            'object_is_uri': isinstance(obj, URIRef),
        }
        predicates.append(entry)
        if predicate_local in SURFACE_LITERAL_PREDICATES and not isinstance(obj, URIRef):
            literals.append({'predicate': predicate_local, 'value': obj_value})
    return {
        'uri': uri,
        'local_name': normalize_uri(uri),
        'types': types,
        'predicates': predicates,
        'surface_literals': literals,
    }


def best_surface_literal(entity_description: dict[str, Any], expected_answer: str) -> tuple[str | None, float]:
    best_value = None
    best_score = -1.0
    expected_norm = normalize_answer_text(expected_answer)
    expected_keys = extract_key_literals(expected_answer)
    for literal in entity_description.get('surface_literals', []):
        value = literal['value']
        value_norm = normalize_answer_text(value)
        overlap = overlap_ratio(expected_answer, value)
        seq_ratio = SequenceMatcher(None, expected_norm, value_norm).ratio() if expected_norm and value_norm else 0.0
        key_hits = len(set(expected_keys) & set(extract_key_literals(value)))
        score = overlap + seq_ratio + (0.2 * key_hits)
        if literal['predicate'] in {'identificador', 'label'}:
            score += 0.15
        if score > best_score:
            best_score = score
            best_value = value
    return best_value, round(best_score, 4)


def collect_candidate_entities(graph: Graph, entity_description: dict[str, Any], expected_answer: str, limit: int = 6) -> list[dict[str, Any]]:
    chosen_uri = entity_description['uri']
    chosen_types = entity_description.get('types', [])
    expected_norm = normalize_answer_text(expected_answer)
    expected_keys = extract_key_literals(expected_answer)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def score_entity(uri: str) -> tuple[float, str | None, str]:
        description = describe_entity(graph, uri)
        best_value, best_score = best_surface_literal(description, expected_answer)
        key_overlap = len(set(expected_keys) & set(extract_key_literals(best_value or '')))
        reason = 'same_type_candidate' if any(description.get('types')) else 'lexical_candidate'
        total = best_score + (0.25 * key_overlap)
        if expected_norm and normalize_answer_text(normalize_uri(uri)) in expected_norm:
            total += 0.2
        return total, best_value, reason

    for type_uri in chosen_types:
        for subject in graph.subjects(RDF.type, URIRef(type_uri)):
            subject_str = str(subject)
            if subject_str == chosen_uri or subject_str in seen:
                continue
            seen.add(subject_str)
            total, best_value, reason = score_entity(subject_str)
            if total <= 0.35:
                continue
            candidates.append(
                {
                    'uri': subject_str,
                    'local_name': normalize_uri(subject_str),
                    'types': [normalize_uri(type_uri)],
                    'best_surface_literal': best_value,
                    'candidate_score': round(total, 4),
                    'candidate_reason': reason,
                }
            )

    for _, _, obj in graph.triples((URIRef(chosen_uri), None, None)):
        if not isinstance(obj, URIRef):
            continue
        obj_str = str(obj)
        if obj_str in seen:
            continue
        seen.add(obj_str)
        total, best_value, reason = score_entity(obj_str)
        if total <= 0.35:
            continue
        candidates.append(
            {
                'uri': obj_str,
                'local_name': normalize_uri(obj_str),
                'types': [normalize_uri(t) for t in describe_entity(graph, obj_str).get('types', [])],
                'best_surface_literal': best_value,
                'candidate_score': round(total, 4),
                'candidate_reason': 'neighbor_candidate',
            }
        )

    candidates.sort(key=lambda item: (-item['candidate_score'], item['local_name']))
    return candidates[:limit]


def classify_reference_gap(result: dict[str, Any], resolution_entry: dict[str, Any] | None, key_literal_hit: bool, surface_quality: str) -> str:
    if surface_quality == 'identifier_heavy':
        return 'identifier_instead_of_surface'
    if resolution_entry and resolution_entry.get('best_candidate_beats_chosen'):
        return 'better_literal_exists'
    if result.get('expected_key_literals') and not key_literal_hit:
        return 'canonical_reference_missing'
    return 'none'


def classify_structural_gap(result: dict[str, Any], resolution_entry: dict[str, Any] | None) -> tuple[str, str]:
    if result['final_boundedness'] != 'bounded' or any(step.get('boundedness_status') != 'bounded' for step in result.get('trace', [])):
        return 'boundedness_gap', 'non_bounded_query_step'
    if not result['rows'] and result.get('confidence', {}).get('overall', 0.0) >= 0.55 and not result.get('fallback_used'):
        return 'planner_gap', 'no_rows_with_confident_plan'
    if resolution_entry and resolution_entry.get('suggested_structural_issue') == 'graph_linking_gap':
        return 'graph_linking_gap', 'related_entity_present_but_expected_path_missing'
    if resolution_entry and resolution_entry.get('suggested_structural_issue') == 'graph_canonicalization_gap':
        return 'graph_canonicalization_gap', 'better_canonical_candidate_detected'
    if result['answer_surface_quality'] == 'identifier_heavy':
        return 'missing_value_surface', 'identifier_rendered_instead_of_human_surface'
    if result['answer_reference_gap'] == 'canonical_reference_missing':
        return 'answer_reference_mismatch', 'expected_reference_not_present_in_answer_surface'
    if result['answer_match_mode'] == 'none':
        if result['selected_evidence_count'] > 0:
            return 'graph_linking_gap', 'evidence_selected_but_not_answering_expected_relation'
        return 'planner_gap', 'no_answer_match_and_no_selected_evidence'
    if result['selected_evidence_count'] > 0 and result['answer_match_mode'] in {'partial', 'weak'} and result['answer_surface_quality'] in {'acceptable', 'overspecified'}:
        return 'synthesis_surface_gap', 'evidence_found_but_surface_answer_is_weak'
    if result['selected_evidence_count'] > 0 and result['answer_match_mode'] in {'exact', 'high_partial'} and result['chosen_entity_uri']:
        return 'needs_expected_uris_promotion', 'stable_answer_and_clear_entity_candidate'
    return 'ok_structurally', 'no_dominant_structural_issue_detected'


def build_resolution_entry(graph: Graph, result: dict[str, Any]) -> dict[str, Any] | None:
    chosen_entity_uri = result.get('chosen_entity_uri')
    if not chosen_entity_uri:
        return None
    description = describe_entity(graph, chosen_entity_uri)
    chosen_best_literal, chosen_best_score = best_surface_literal(description, result['expected_answer_text'])
    candidate_entities = collect_candidate_entities(graph, description, result['expected_answer_text'])
    best_candidate = candidate_entities[0] if candidate_entities else None
    best_candidate_beats_chosen = bool(
        best_candidate
        and best_candidate['candidate_score'] >= max(chosen_best_score + 0.2, 0.85)
    )
    suggested_issue = None
    if best_candidate_beats_chosen:
        suggested_issue = 'graph_canonicalization_gap'
    elif result['rows'] and not chosen_best_literal and candidate_entities:
        suggested_issue = 'graph_linking_gap'
    entry = {
        'question_id': result['question_id'],
        'chosen_entity_uri': chosen_entity_uri,
        'chosen_entity_type': [normalize_uri(item) for item in description.get('types', [])],
        'chosen_best_surface_literal': chosen_best_literal,
        'chosen_best_surface_score': chosen_best_score,
        'candidate_entities': candidate_entities,
        'candidate_reason': best_candidate['candidate_reason'] if best_candidate else None,
        'best_surface_literal': best_candidate['best_surface_literal'] if best_candidate else None,
        'best_candidate_beats_chosen': best_candidate_beats_chosen,
        'suggested_structural_issue': suggested_issue,
    }
    return entry


def load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def build_summary(results: list[dict[str, Any]], resolution_entries: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        'total_questions': len(results),
        'structural_gap_counts': dict(Counter(item['structural_gap_category'] for item in results)),
        'intent_counts': dict(Counter(item['intent'] for item in results if item.get('intent'))),
        'plan_family_counts': dict(Counter(item['plan_family'] for item in results if item.get('plan_family'))),
        'match_mode_counts': dict(Counter(item['answer_match_mode'] for item in results)),
        'surface_quality_counts': dict(Counter(item['answer_surface_quality'] for item in results)),
        'avg_plan_confidence': round(mean(item.get('confidence', {}).get('overall', 0.0) for item in results) if results else 0.0, 4),
        'avg_row_count': round(mean(len(item.get('rows', [])) for item in results) if results else 0.0, 4),
    }
    entity_counter = Counter(entry['chosen_entity_uri'] for entry in resolution_entries if entry and entry.get('chosen_entity_uri'))
    candidate_issue_counter = Counter(entry['suggested_structural_issue'] for entry in resolution_entries if entry and entry.get('suggested_structural_issue'))
    repeated_patterns = []
    pattern_counter = Counter((item['structural_gap_category'], item.get('plan_family')) for item in results)
    for (category, family), count in pattern_counter.most_common(8):
        repeated_patterns.append({'structural_gap_category': category, 'plan_family': family, 'count': count})
    return {
        'summary': summary,
        'top_problematic_entities': [{'entity_uri': uri, 'count': count} for uri, count in entity_counter.most_common(8)],
        'candidate_issue_counts': dict(candidate_issue_counter),
        'repeated_patterns': repeated_patterns,
        'top_structurally_good_questions': [
            {
                'question_id': item['question_id'],
                'question': item['question'],
                'plan_family': item.get('plan_family'),
                'answer_match_mode': item['answer_match_mode'],
                'chosen_entity_uri': item.get('chosen_entity_uri'),
            }
            for item in results
            if item['structural_gap_category'] in {'needs_expected_uris_promotion', 'ok_structurally'}
        ][:10],
    }


def build_promotion_candidates(results: list[dict[str, Any]], resolution_entries: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    candidates = []
    for item in results:
        if item['structural_gap_category'] not in {'ok_structurally', 'needs_expected_uris_promotion'}:
            continue
        if item['answer_match_mode'] not in {'exact', 'high_partial'}:
            continue
        chosen_uri = item.get('chosen_entity_uri')
        resolution = resolution_entries.get(item['question_id'])
        candidate_expected = [chosen_uri] if chosen_uri else []
        if not candidate_expected and resolution and resolution.get('candidate_entities'):
            candidate_expected = [resolution['candidate_entities'][0]['uri']]
        candidates.append(
            {
                'question_id': item['question_id'],
                'question': item['question'],
                'promote_to_formal_eval': bool(candidate_expected),
                'candidate_expected_uris': candidate_expected,
                'promotion_reason': item['structural_gap_rationale'],
            }
        )
    return {
        'summary': {
            'total_candidates': len(candidates),
            'promotable_candidates': sum(1 for item in candidates if item['promote_to_formal_eval']),
        },
        'results': candidates,
    }


def decide_next_change(summary_payload: dict[str, Any]) -> tuple[str, str]:
    counts = Counter(summary_payload['summary']['structural_gap_counts'])
    for category in ['needs_expected_uris_promotion', 'ok_structurally']:
        counts.pop(category, None)
    if not counts:
        return 'formalize_promotable_sandbox_questions', 'stable_structural_behavior_detected'
    dominant, _ = counts.most_common(1)[0]
    mapping = {
        'graph_canonicalization_gap': 'canonical_entity_consolidation',
        'graph_linking_gap': 'structural_link_completion',
        'missing_value_surface': 'surface_literal_enrichment',
        'planner_gap': 'planner_generalization_tuning',
        'boundedness_gap': 'boundedness_policy_tuning',
        'synthesis_surface_gap': 'surface_synthesis_polish',
        'answer_reference_mismatch': 'canonical_reference_alignment',
    }
    return mapping.get(dominant, 'structural_gap_triage'), dominant


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def run_diagnostic(args: argparse.Namespace) -> None:
    dataset = load_dataset(args.qa_file)
    if args.limit > 0:
        dataset = dataset[: args.limit]
    graph = load_graph(args.tbox_file, args.abox_file)
    schema = load_schema()
    uri_index = build_local_uri_index(graph)
    planner_catalog = load_json_if_exists(PLANNER_GENERALIZATION_CATALOG_PATH)
    boundedness_matrix = load_json_if_exists(BOUNDEDNESS_POLICY_MATRIX_PATH)

    results: list[dict[str, Any]] = []
    resolution_entries: list[dict[str, Any]] = []
    resolution_by_question: dict[str, dict[str, Any] | None] = {}

    for index, item in enumerate(dataset, 1):
        question = item['question']
        print(f'[{index}/{len(dataset)}] {item["question_id"]}: {question}')
        plan = build_query_plan(question, schema, graph)
        execution = execute_query_plan(plan, graph)
        synthesis_answer, synthesis_trace = synthesize_answer(question, rows_for_synthesis(execution), plan)
        synthesis_trace_dict = asdict(synthesis_trace)
        uri_map = extract_uri_map(execution.raw_bindings)
        selected_evidence = synthesis_trace_dict.get('selected_evidence', [])
        normalized_values = synthesis_trace_dict.get('normalized_values', [])
        expected_answer_text = item['answer']
        match_mode, key_literal_hit, overlap, expected_keys = classify_match(expected_answer_text, synthesis_answer)
        surface_quality = classify_surface_quality(expected_answer_text, synthesis_answer, match_mode)
        result = {
            **item,
            'expected_answer_text': expected_answer_text,
            'plan_family': plan.plan_family,
            'template_id': plan.template_id,
            'predicted_hop_depth': plan.predicted_hop_depth,
            'anchor_text': plan.anchor_text,
            'anchor_candidates': plan.anchor_candidates,
            'confidence': plan.confidence,
            'recommended_action': plan.recommended_action,
            'final_boundedness': execution.trace.final_boundedness,
            'queries': [asdict(step) for step in plan.steps],
            'trace': [asdict(step) for step in execution.trace.steps],
            'rows': [list(row) for row in execution.rows],
            'query_debug': plan.debug,
            'selected_evidence': selected_evidence,
            'normalized_values': normalized_values,
            'pre_polish_answer': synthesis_trace_dict.get('pre_polish_answer'),
            'synthesized_answer': synthesis_answer,
            'synthesis_trace': synthesis_trace_dict,
            'answer_match_mode': match_mode,
            'answer_key_literal_hit': key_literal_hit,
            'answer_overlap_ratio': overlap,
            'answer_surface_quality': surface_quality,
            'expected_key_literals': expected_keys,
            'selected_evidence_count': len(selected_evidence),
            '_raw_bindings': [tuple(row) for row in execution.raw_bindings],
            '_uri_map': uri_map,
        }
        chosen_entity_uri = choose_entity_uri(result, uri_index)
        result['chosen_entity_uri'] = chosen_entity_uri
        resolution_entry = build_resolution_entry(graph, result) if chosen_entity_uri else None
        result['answer_reference_gap'] = classify_reference_gap(result, resolution_entry, key_literal_hit, surface_quality)
        category, rationale = classify_structural_gap(result, resolution_entry)
        result['structural_gap_category'] = category
        result['structural_gap_rationale'] = rationale
        resolution_by_question[item['question_id']] = resolution_entry
        if resolution_entry is not None:
            resolution_entries.append(resolution_entry)
        results.append(result)
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    report = {
        'summary': {
            'total_questions': len(results),
            'dataset_path': str(args.qa_file),
            'tbox_path': str(args.tbox_file),
            'abox_path': str(args.abox_file),
            'schema_condensed_path': str(SCHEMA_CONDENSED_PATH),
            'planner_catalog_loaded': planner_catalog is not None,
            'boundedness_matrix_loaded': boundedness_matrix is not None,
        },
        'results': [
            {key: value for key, value in item.items() if not key.startswith('_')}
            for item in results
        ],
    }
    write_json(args.report_path, report)

    summary_payload = build_summary(results, resolution_entries)
    write_json(args.summary_path, summary_payload)

    resolution_payload = {
        'summary': {
            'questions_with_resolution_candidates': len(resolution_entries),
            'questions_with_better_candidate': sum(1 for item in resolution_entries if item.get('best_candidate_beats_chosen')),
        },
        'results': resolution_entries,
    }
    write_json(args.resolution_candidates_path, resolution_payload)

    promotion_payload = build_promotion_candidates(results, resolution_by_question)
    write_json(args.promotion_path, promotion_payload)

    next_change, dominant_issue = decide_next_change(summary_payload)
    decision_payload = {
        'summary': summary_payload['summary'],
        'dominant_structural_gap_category': dominant_issue,
        'distribution': summary_payload['summary']['structural_gap_counts'],
        'top_problematic_entities': summary_payload['top_problematic_entities'],
        'top_repeated_patterns': summary_payload['repeated_patterns'][:5],
        'promotable_question_ids': [
            item['question_id']
            for item in promotion_payload['results']
            if item['promote_to_formal_eval']
        ],
        'recommended_t17_change': next_change,
    }
    write_json(args.decision_path, decision_payload)

    print('')
    print(f"Diagnostic report: {args.report_path}")
    print(f"Structural summary: {args.summary_path}")
    print(f"Resolution candidates: {args.resolution_candidates_path}")
    print(f"Promotion candidates: {args.promotion_path}")
    print(f"Decision report: {args.decision_path}")


if __name__ == '__main__':
    run_diagnostic(parse_args())
