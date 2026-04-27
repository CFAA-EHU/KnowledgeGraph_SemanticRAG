from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
from collections import Counter
from typing import Any

from rdflib import Graph, URIRef

from artifact_contracts import (
    ABOX_MINTED_ENTITY_REGISTRY_PATH,
    ENRICHED_ABOX_PATH,
    ENRICHMENT_DECISION_REPORT_PATH,
    LINK_COMPLETION_CANDIDATES_PATH,
    LINK_COMPLETION_MAP_PATH,
    LINK_COMPLETION_REPORT_PATH,
    OPERATIONAL_ABOX_PATH,
    SANDBOX_DIAGNOSTIC_REPORT_PATH,
    SANDBOX_ENTITY_RESOLUTION_CANDIDATES_PATH,
    SANDBOX_STRUCTURAL_GAP_SUMMARY_PATH,
    OPERATIONAL_TBOX_PATH,
)
from abox_graph_sanitizer import load_mint_registry, sanitize_abox_graph, save_mint_registry

EXTRACTION_DIR = Path(__file__).resolve().parent
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

from link_completion_policy import (
    build_link_completion_candidates,
    candidates_to_jsonable,
    detect_residual_links,
    links_to_jsonable,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Complete only the residual high-confidence link families over the enriched A-Box before runtime consumption.')
    parser.add_argument('--input', type=Path, default=ENRICHED_ABOX_PATH, help='Enriched A-Box path.')
    parser.add_argument('--output', type=Path, default=OPERATIONAL_ABOX_PATH, help='Linked operational A-Box path.')
    parser.add_argument('--candidates-path', type=Path, default=LINK_COMPLETION_CANDIDATES_PATH, help='Residual link completion candidate corpus path.')
    parser.add_argument('--map-path', type=Path, default=LINK_COMPLETION_MAP_PATH, help='Added residual link traceability path.')
    parser.add_argument('--report-path', type=Path, default=LINK_COMPLETION_REPORT_PATH, help='Residual link completion report path.')
    parser.add_argument('--sandbox-summary-path', type=Path, default=SANDBOX_STRUCTURAL_GAP_SUMMARY_PATH, help='Latest sandbox structural summary path.')
    parser.add_argument('--sandbox-report-path', type=Path, default=SANDBOX_DIAGNOSTIC_REPORT_PATH, help='Latest sandbox diagnostic report path.')
    parser.add_argument('--sandbox-candidates-path', type=Path, default=SANDBOX_ENTITY_RESOLUTION_CANDIDATES_PATH, help='Latest sandbox entity resolution candidates path.')
    parser.add_argument('--enrichment-decision-path', type=Path, default=ENRICHMENT_DECISION_REPORT_PATH, help='T18 enrichment decision report path.')
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def load_graph(path: Path) -> Graph:
    if not path.exists():
        raise SystemExit(f'Missing A-Box input: {path}')
    graph = Graph()
    graph.parse(path, format='turtle')
    return graph


def clone_graph(graph: Graph) -> Graph:
    linked = Graph()
    for triple in graph:
        linked.add(triple)
    return linked


def apply_links(base_graph: Graph, links) -> tuple[Graph, dict[str, Any], list[dict[str, Any]]]:
    linked = clone_graph(base_graph)
    affected_entities: set[str] = set()
    added_links = []
    already_present = []
    for item in links:
        triple = (URIRef(item.source_uri), URIRef(item.predicate), URIRef(item.target_uri))
        if triple in linked:
            already_present.append({
                'source_uri': item.source_uri,
                'predicate': item.predicate,
                'target_uri': item.target_uri,
                'link_family': item.link_family,
            })
            continue
        linked.add(triple)
        affected_entities.add(item.source_uri)
        affected_entities.add(item.target_uri)
        added_links.append(item)
    return linked, {
        'input_triples': len(base_graph),
        'output_triples': len(linked),
        'added_link_count': len(added_links),
        'already_present_count': len(already_present),
        'added_family_count': len({item.link_family for item in added_links}),
        'added_target_count': len({item.target_uri for item in added_links}),
        'affected_entities_count': len(affected_entities),
        'affected_entities': sorted(affected_entities),
    }, already_present


def main() -> None:
    args = parse_args()
    enriched_graph = load_graph(args.input)
    sandbox_summary = load_json(args.sandbox_summary_path)
    sandbox_report = load_json(args.sandbox_report_path)
    sandbox_candidates = load_json(args.sandbox_candidates_path)
    enrichment_decision = load_json(args.enrichment_decision_path)

    candidates = build_link_completion_candidates(
        enriched_graph,
        sandbox_summary,
        sandbox_report,
        enrichment_decision,
        sandbox_candidates,
    )
    candidate_payload = {
        'summary': {
            'total_candidates': len(candidates),
            'active_candidates': sum(1 for item in candidates if item.candidate_status == 'whitelisted_active'),
            'blocked_candidates': sum(1 for item in candidates if item.candidate_status == 'whitelisted_blocked'),
            'families': [item.family for item in candidates],
            'dominant_gap_after_t18': enrichment_decision.get('summary', {}).get('dominant_gap_after_t18'),
        },
        'results': candidates_to_jsonable(candidates),
    }
    write_json(args.candidates_path, candidate_payload)

    links = detect_residual_links(enriched_graph, candidates)
    linked_graph, stats, already_present = apply_links(enriched_graph, links)
    tbox_graph = load_graph(OPERATIONAL_TBOX_PATH)
    mint_registry = load_mint_registry(ABOX_MINTED_ENTITY_REGISTRY_PATH)
    linked_graph, sanitization_result = sanitize_abox_graph(
        linked_graph,
        tbox_graph=tbox_graph,
        mint_registry=mint_registry,
    )
    save_mint_registry(mint_registry, ABOX_MINTED_ENTITY_REGISTRY_PATH)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    linked_graph.serialize(destination=args.output, format='turtle')

    write_json(
        args.map_path,
        {
            'summary': {
                'link_additions': stats['added_link_count'],
                'already_present_links': stats['already_present_count'],
            },
            'results': links_to_jsonable(links),
            'already_present': already_present,
        },
    )

    active_candidates = [item for item in candidates if item.candidate_status == 'whitelisted_active']
    blocked_candidates = [item for item in candidates if item.candidate_status == 'whitelisted_blocked']
    evidence_mode_breakdown = dict(Counter(item.evidence_type for item in links))
    added_link_count = stats.get('added_link_count', 0)
    evidence_mode_percentages = {
        key: round((value / added_link_count) * 100.0, 2) if added_link_count else 0.0
        for key, value in evidence_mode_breakdown.items()
    }
    blocked_reason_counts = dict(Counter(item.block_reason or 'unspecified_block_reason' for item in blocked_candidates))
    report_payload = {
        'summary': {
            **stats,
            'sanitization': sanitization_result.to_manifest_summary(),
            'input_path': str(args.input),
            'output_path': str(args.output),
            'candidates_path': str(args.candidates_path),
            'map_path': str(args.map_path),
            'active_family_count': len(active_candidates),
            'blocked_family_count': len(blocked_candidates),
            'active_family_names': [item.family for item in active_candidates],
            'blocked_family_names': [item.family for item in blocked_candidates],
            'blocked_reason_counts': blocked_reason_counts,
            'evidence_mode_breakdown': evidence_mode_breakdown,
            'evidence_mode_percentages': evidence_mode_percentages,
            'rule_counts': dict(Counter(item.rule_id for item in links)),
            'baseline_dominant_issue': enrichment_decision.get('summary', {}).get('dominant_gap_after_t18'),
        },
        'links_added': links_to_jsonable(links),
        'blocked_candidates': candidates_to_jsonable(blocked_candidates),
        'already_present_links': already_present,
    }
    write_json(args.report_path, report_payload)

    print(f'[link-completer] Enriched A-Box input: {args.input}')
    print(f'[link-completer] Linked operational A-Box: {args.output}')
    print(f'[link-completer] Candidate families: {len(candidates)}')
    print(f'[link-completer] Active families: {len(active_candidates)}')
    print(f'[link-completer] Added links: {stats["added_link_count"]}')
    print(f'[link-completer] Output triples: {stats["output_triples"]}')


if __name__ == '__main__':
    main()
