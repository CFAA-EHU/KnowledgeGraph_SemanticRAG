import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
from typing import Any

from rdflib import Graph, URIRef

from artifact_contracts import (
    CANONICAL_ENTITY_MAP_PATH,
    CANONICALIZATION_REPORT_PATH,
    CANONICALIZATION_RESOLUTION_CANDIDATES_PATH,
    OPERATIONAL_ABOX_PATH,
    RAW_MERGED_ABOX_PATH,
    SANDBOX_DECISION_REPORT_PATH,
    SANDBOX_DIAGNOSTIC_REPORT_PATH,
    SANDBOX_ENTITY_RESOLUTION_CANDIDATES_PATH,
    SANDBOX_STRUCTURAL_GAP_SUMMARY_PATH,
)
EXTRACTION_DIR = Path(__file__).resolve().parent
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

from canonical_resolution_policy import (
    candidates_to_jsonable,
    clusters_to_jsonable,
    collect_resolution_diagnostics,
    group_resolution_candidates,
    selections_to_jsonable,
    select_canonical_entity,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Canonicalize the operational merged A-Box after the merge stage.')
    parser.add_argument('--input', type=Path, default=RAW_MERGED_ABOX_PATH, help='Raw merged A-Box path.')
    parser.add_argument('--output', type=Path, default=OPERATIONAL_ABOX_PATH, help='Canonical operational A-Box path.')
    parser.add_argument('--resolution-candidates-path', type=Path, default=CANONICALIZATION_RESOLUTION_CANDIDATES_PATH, help='Canonicalization resolution corpus path.')
    parser.add_argument('--entity-map-path', type=Path, default=CANONICAL_ENTITY_MAP_PATH, help='Absorbed-to-canonical mapping path.')
    parser.add_argument('--report-path', type=Path, default=CANONICALIZATION_REPORT_PATH, help='Canonicalization report path.')
    parser.add_argument('--sandbox-candidates-path', type=Path, default=SANDBOX_ENTITY_RESOLUTION_CANDIDATES_PATH, help='T16 entity resolution candidates path.')
    parser.add_argument('--sandbox-summary-path', type=Path, default=SANDBOX_STRUCTURAL_GAP_SUMMARY_PATH, help='T16 structural summary path.')
    parser.add_argument('--sandbox-decision-path', type=Path, default=SANDBOX_DECISION_REPORT_PATH, help='T16 decision report path.')
    parser.add_argument('--sandbox-report-path', type=Path, default=SANDBOX_DIAGNOSTIC_REPORT_PATH, help='Detailed T16 sandbox report path.')
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


def resolve_mapping_chain(initial_mapping: dict[str, str]) -> dict[str, str]:
    def resolve(uri: str) -> str:
        seen: set[str] = set()
        current = uri
        while current in initial_mapping and current not in seen:
            seen.add(current)
            current = initial_mapping[current]
        return current
    return {source: resolve(target) for source, target in initial_mapping.items()}


def rewrite_graph(raw_graph: Graph, selections) -> tuple[Graph, dict[str, Any], dict[str, dict[str, Any]]]:
    initial_mapping = {
        selection.source_uri: selection.canonical_uri
        for selection in selections
        if selection.source_uri != selection.canonical_uri
    }
    final_mapping = resolve_mapping_chain(initial_mapping)
    resolved_selections: dict[str, dict[str, Any]] = {}
    for selection in selections:
        final_canonical = final_mapping.get(selection.canonical_uri, selection.canonical_uri)
        supplemental_targets = []
        for uri in selection.supplemental_targets:
            resolved = final_mapping.get(uri, uri)
            if resolved != final_canonical and resolved not in supplemental_targets:
                supplemental_targets.append(resolved)
        resolved_selections[selection.source_uri] = {
            'canonical_uri': final_canonical,
            'entity_type': selection.entity_type,
            'resolution_reason': selection.resolution_reason,
            'rules_applied': selection.rules_applied,
            'support_question_ids': selection.support_question_ids,
            'supplemental_targets': supplemental_targets,
            'selection_scores': selection.selection_scores,
        }

    canonical_graph = Graph()
    rewritten_triples = 0
    skipped_self_loops = 0
    rewritten_subjects = 0
    rewritten_objects = 0

    for subject, predicate, obj in raw_graph:
        new_subject = subject
        new_object = obj
        if isinstance(subject, URIRef):
            subject_uri = str(subject)
            if subject_uri in final_mapping:
                new_subject = URIRef(final_mapping[subject_uri])
                if new_subject != subject:
                    rewritten_subjects += 1
        if isinstance(obj, URIRef):
            object_uri = str(obj)
            if object_uri in final_mapping:
                new_object = URIRef(final_mapping[object_uri])
                if new_object != obj:
                    rewritten_objects += 1
        if isinstance(new_object, URIRef) and new_subject == new_object and (new_subject != subject or new_object != obj):
            skipped_self_loops += 1
            continue
        if new_subject != subject or new_object != obj:
            rewritten_triples += 1
        canonical_graph.add((new_subject, predicate, new_object))

    supplemental_links_added = 0
    for source_uri, metadata in resolved_selections.items():
        if not metadata['supplemental_targets']:
            continue
        source_ref = URIRef(source_uri)
        incoming_links = list(raw_graph.subject_predicates(source_ref))
        for incoming_subject, predicate in incoming_links:
            resolved_subject_uri = final_mapping.get(str(incoming_subject), str(incoming_subject))
            resolved_subject_ref = URIRef(resolved_subject_uri)
            for target_uri in metadata['supplemental_targets']:
                target_ref = URIRef(target_uri)
                if resolved_subject_ref == target_ref:
                    continue
                triple = (resolved_subject_ref, predicate, target_ref)
                if triple not in canonical_graph:
                    canonical_graph.add(triple)
                    supplemental_links_added += 1

    entity_map = {
        source_uri: {
            'canonical_uri': metadata['canonical_uri'],
            'resolution_reason': metadata['resolution_reason'],
            'entity_type': metadata['entity_type'],
            'rules_applied': metadata['rules_applied'],
            'support_question_ids': metadata['support_question_ids'],
            'supplemental_targets': metadata['supplemental_targets'],
        }
        for source_uri, metadata in resolved_selections.items()
        if source_uri != metadata['canonical_uri']
    }

    rewrite_stats = {
        'raw_triples': len(raw_graph),
        'canonical_triples': len(canonical_graph),
        'rewritten_triples': rewritten_triples,
        'rewritten_subjects': rewritten_subjects,
        'rewritten_objects': rewritten_objects,
        'skipped_self_loops': skipped_self_loops,
        'supplemental_links_added': supplemental_links_added,
        'absorbed_nodes_count': len(entity_map),
    }
    return canonical_graph, rewrite_stats, entity_map


def main() -> None:
    args = parse_args()
    raw_graph = load_graph(args.input)
    sandbox_candidates = load_json(args.sandbox_candidates_path)
    sandbox_summary = load_json(args.sandbox_summary_path)
    sandbox_decision = load_json(args.sandbox_decision_path)
    sandbox_report = load_json(args.sandbox_report_path)

    diagnostics = collect_resolution_diagnostics(
        raw_graph,
        sandbox_candidates,
        sandbox_summary,
        sandbox_decision,
        sandbox_report,
    )
    accepted_candidates = diagnostics['accepted']
    clusters = group_resolution_candidates(accepted_candidates)
    selections = [select_canonical_entity(cluster, raw_graph) for cluster in clusters]

    resolution_payload = {
        'summary': diagnostics['summary'],
        'results': candidates_to_jsonable(accepted_candidates),
        'discarded': diagnostics['discarded'],
    }
    write_json(args.resolution_candidates_path, resolution_payload)

    canonical_graph, rewrite_stats, entity_map = rewrite_graph(raw_graph, selections)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canonical_graph.serialize(destination=args.output, format='turtle')
    write_json(args.entity_map_path, entity_map)

    report_payload = {
        'summary': {
            **rewrite_stats,
            'input_path': str(args.input),
            'output_path': str(args.output),
            'resolution_candidates_path': str(args.resolution_candidates_path),
            'entity_map_path': str(args.entity_map_path),
        },
        'clusters_processed': clusters_to_jsonable(clusters),
        'selections': selections_to_jsonable(selections),
        'discarded_candidates': diagnostics['discarded'],
    }
    write_json(args.report_path, report_payload)

    print(f'[canonicalizer] Raw merged A-Box: {args.input}')
    print(f'[canonicalizer] Canonical operational A-Box: {args.output}')
    print(f'[canonicalizer] Accepted resolution candidates: {len(accepted_candidates)}')
    print(f'[canonicalizer] Absorbed nodes: {rewrite_stats["absorbed_nodes_count"]}')
    print(f'[canonicalizer] Supplemental links added: {rewrite_stats["supplemental_links_added"]}')
    print(f'[canonicalizer] Canonical triples: {rewrite_stats["canonical_triples"]}')


if __name__ == '__main__':
    main()
