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

from rdflib import Graph, Literal, URIRef

from artifact_contracts import (
    CANONICALIZATION_REPORT_PATH,
    ENRICHMENT_LINK_MAP_PATH,
    ENRICHMENT_REPORT_PATH,
    ENRICHMENT_RESOLUTION_CANDIDATES_PATH,
    ENRICHMENT_SURFACE_MAP_PATH,
    OPERATIONAL_ABOX_PATH,
    CANONICAL_ABOX_PATH,
    SANDBOX_DECISION_REPORT_PATH,
    SANDBOX_DIAGNOSTIC_REPORT_PATH,
    SANDBOX_STRUCTURAL_GAP_SUMMARY_PATH,
    SANDBOX_ENTITY_RESOLUTION_CANDIDATES_PATH,
)

EXTRACTION_DIR = Path(__file__).resolve().parent
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

from enrichment_policy import (
    build_enrichment_corpus,
    candidates_to_jsonable,
    detect_link_enrichments,
    detect_surface_enrichments,
    links_to_jsonable,
    surfaces_to_jsonable,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Enrich the canonical A-Box with residual linking and surface improvements before runtime consumption.')
    parser.add_argument('--input', type=Path, default=CANONICAL_ABOX_PATH, help='Canonical A-Box path.')
    parser.add_argument('--output', type=Path, default=OPERATIONAL_ABOX_PATH, help='Enriched operational A-Box path.')
    parser.add_argument('--resolution-candidates-path', type=Path, default=ENRICHMENT_RESOLUTION_CANDIDATES_PATH, help='Enrichment candidate corpus path.')
    parser.add_argument('--link-map-path', type=Path, default=ENRICHMENT_LINK_MAP_PATH, help='Added link traceability path.')
    parser.add_argument('--surface-map-path', type=Path, default=ENRICHMENT_SURFACE_MAP_PATH, help='Added surface traceability path.')
    parser.add_argument('--report-path', type=Path, default=ENRICHMENT_REPORT_PATH, help='Enrichment report path.')
    parser.add_argument('--sandbox-summary-path', type=Path, default=SANDBOX_STRUCTURAL_GAP_SUMMARY_PATH, help='Latest sandbox structural summary path.')
    parser.add_argument('--sandbox-candidates-path', type=Path, default=SANDBOX_ENTITY_RESOLUTION_CANDIDATES_PATH, help='Latest sandbox entity resolution candidates path.')
    parser.add_argument('--sandbox-decision-path', type=Path, default=SANDBOX_DECISION_REPORT_PATH, help='Latest sandbox decision report path.')
    parser.add_argument('--sandbox-report-path', type=Path, default=SANDBOX_DIAGNOSTIC_REPORT_PATH, help='Detailed sandbox diagnostic report path.')
    parser.add_argument('--canonicalization-report-path', type=Path, default=CANONICALIZATION_REPORT_PATH, help='Canonicalization report path.')
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
    enriched = Graph()
    for triple in graph:
        enriched.add(triple)
    return enriched


def apply_enrichments(base_graph: Graph, links, surfaces) -> tuple[Graph, dict[str, Any]]:
    enriched = clone_graph(base_graph)
    affected_entities: set[str] = set()
    added_link_count = 0
    added_surface_count = 0
    for item in links:
        triple = (URIRef(item.source_uri), URIRef(item.predicate_uri), URIRef(item.target_uri))
        if triple in enriched:
            continue
        enriched.add(triple)
        affected_entities.add(item.source_uri)
        affected_entities.add(item.target_uri)
        added_link_count += 1
    for item in surfaces:
        triple = (URIRef(item.entity_uri), URIRef(item.added_property_uri), Literal(item.added_value))
        if triple in enriched:
            continue
        enriched.add(triple)
        affected_entities.add(item.entity_uri)
        added_surface_count += 1
    return enriched, {
        'input_triples': len(base_graph),
        'output_triples': len(enriched),
        'added_link_count': added_link_count,
        'added_surface_count': added_surface_count,
        'affected_entities_count': len(affected_entities),
        'affected_entities': sorted(affected_entities),
    }


def main() -> None:
    args = parse_args()
    canonical_graph = load_graph(args.input)
    sandbox_summary = load_json(args.sandbox_summary_path)
    sandbox_candidates = load_json(args.sandbox_candidates_path)
    sandbox_decision = load_json(args.sandbox_decision_path)
    sandbox_report = load_json(args.sandbox_report_path)
    canonicalization_report = load_json(args.canonicalization_report_path)

    corpus_diagnostics = build_enrichment_corpus(
        canonical_graph,
        sandbox_summary,
        sandbox_candidates,
        sandbox_decision,
        canonicalization_report,
        sandbox_report,
    )
    accepted_candidates = corpus_diagnostics['accepted']
    discarded_candidates = corpus_diagnostics['discarded']
    links = detect_link_enrichments(canonical_graph, accepted_candidates)
    surfaces = detect_surface_enrichments(canonical_graph, accepted_candidates, links)
    enriched_graph, stats = apply_enrichments(canonical_graph, links, surfaces)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    enriched_graph.serialize(destination=args.output, format='turtle')
    resolution_payload = {
        'summary': corpus_diagnostics['summary'],
        'results': candidates_to_jsonable(accepted_candidates),
        'discarded': discarded_candidates,
    }
    write_json(args.resolution_candidates_path, resolution_payload)
    write_json(args.link_map_path, {'summary': {'link_additions': len(links)}, 'results': links_to_jsonable(links)})
    write_json(args.surface_map_path, {'summary': {'surface_additions': len(surfaces)}, 'results': surfaces_to_jsonable(surfaces)})

    report_payload = {
        'summary': {
            **stats,
            'input_path': str(args.input),
            'output_path': str(args.output),
            'resolution_candidates_path': str(args.resolution_candidates_path),
            'link_map_path': str(args.link_map_path),
            'surface_map_path': str(args.surface_map_path),
            'baseline_dominant_issue': sandbox_decision.get('dominant_structural_gap_category'),
            'baseline_structural_gap_counts': sandbox_summary.get('summary', {}).get('structural_gap_counts', {}),
            'baseline_promotable_question_ids': sandbox_decision.get('promotable_question_ids', []),
            'link_rule_counts': dict(Counter(item.rule_id for item in links)),
            'surface_rule_counts': dict(Counter(item.rule_id for item in surfaces)),
        },
        'links_added': links_to_jsonable(links),
        'surfaces_added': surfaces_to_jsonable(surfaces),
        'discarded_candidates': discarded_candidates,
    }
    write_json(args.report_path, report_payload)

    print(f'[enricher] Canonical A-Box input: {args.input}')
    print(f'[enricher] Enriched operational A-Box: {args.output}')
    print(f'[enricher] Accepted enrichment candidates: {len(accepted_candidates)}')
    print(f'[enricher] Added links: {stats["added_link_count"]}')
    print(f'[enricher] Added surfaces: {stats["added_surface_count"]}')
    print(f'[enricher] Output triples: {stats["output_triples"]}')


if __name__ == '__main__':
    main()
