import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from artifact_contracts import (
    ABOX_MINTED_ENTITY_REGISTRY_PATH,
    CANONICAL_ABOX_PATH,
    CANONICAL_ANCHORS_PATH,
    CANONICAL_ENTITY_MAP_PATH,
    CANONICALIZATION_REPORT_PATH,
    CANONICALIZATION_RESOLUTION_CANDIDATES_PATH,
    RAW_MERGED_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
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
    collect_identifier_based_candidates,
    collect_resolution_diagnostics,
    collect_surface_variant_diagnostics,
    group_resolution_candidates,
    selections_to_jsonable,
    select_canonical_entity,
)
from abox_graph_sanitizer import load_mint_registry, sanitize_abox_graph, save_mint_registry
from abox_semantic_validator import load_semantic_vocabulary, validate_abox_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Canonicalize the operational merged A-Box after the merge stage.')
    parser.add_argument('--input', type=Path, default=RAW_MERGED_ABOX_PATH, help='Raw merged A-Box path.')
    parser.add_argument('--output', type=Path, default=CANONICAL_ABOX_PATH, help='Canonical operational A-Box path.')
    parser.add_argument('--resolution-candidates-path', type=Path, default=CANONICALIZATION_RESOLUTION_CANDIDATES_PATH, help='Canonicalization resolution corpus path.')
    parser.add_argument('--entity-map-path', type=Path, default=CANONICAL_ENTITY_MAP_PATH, help='Absorbed-to-canonical mapping path.')
    parser.add_argument('--report-path', type=Path, default=CANONICALIZATION_REPORT_PATH, help='Canonicalization report path.')
    parser.add_argument('--sandbox-candidates-path', type=Path, default=SANDBOX_ENTITY_RESOLUTION_CANDIDATES_PATH, help='T16 entity resolution candidates path.')
    parser.add_argument('--sandbox-summary-path', type=Path, default=SANDBOX_STRUCTURAL_GAP_SUMMARY_PATH, help='T16 structural summary path.')
    parser.add_argument('--sandbox-decision-path', type=Path, default=SANDBOX_DECISION_REPORT_PATH, help='T16 decision report path.')
    parser.add_argument('--sandbox-report-path', type=Path, default=SANDBOX_DIAGNOSTIC_REPORT_PATH, help='Detailed T16 sandbox report path.')
    parser.add_argument('--canonical-anchors-path', type=Path, default=CANONICAL_ANCHORS_PATH, help='Explicit canonical anchor declarations.')
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


def _uri_exists(graph: Graph, uri: str) -> bool:
    ref = URIRef(uri)
    return any(graph.triples((ref, None, None))) or any(graph.triples((None, None, ref)))


def load_canonical_anchors(path: Path, graph: Graph | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding='utf-8'))
    anchors = payload.get('anchors', [])
    if not isinstance(anchors, list):
        raise ValueError(f'[canonical_anchors] "anchors" debe ser una lista en {path}')

    canonical_uris = set()
    absorbed_uris = set()
    for anchor in anchors:
        canonical_uri = anchor.get('canonical_uri')
        absorbs = anchor.get('absorbs', [])
        legacy_aliases = anchor.get('legacy_aliases', [])
        if not canonical_uri or not isinstance(absorbs, list) or not isinstance(legacy_aliases, list):
            raise ValueError(f'[canonical_anchors] Anchor invalido: {anchor}')
        if canonical_uri in canonical_uris:
            raise ValueError(f'[canonical_anchors] Canonical URI duplicada: {canonical_uri}')
        canonical_uris.add(canonical_uri)
        if graph is not None and not _uri_exists(graph, canonical_uri):
            raise ValueError(f'[canonical_anchors] canonical_uri no existe en el grafo de entrada: {canonical_uri}')
        for absorbed in absorbs:
            if absorbed == canonical_uri:
                raise ValueError(f'[canonical_anchors] Auto-absorcion: {absorbed}')
            if absorbed in absorbed_uris:
                raise ValueError(f'[canonical_anchors] URI absorbida duplicada en anchors: {absorbed}')
            absorbed_uris.add(absorbed)
            if graph is not None and not _uri_exists(graph, absorbed):
                raise ValueError(f'[canonical_anchors] absorbed URI no existe en el grafo de entrada: {absorbed}')
        for alias in legacy_aliases:
            if alias == canonical_uri:
                raise ValueError(f'[canonical_anchors] Alias legado apunta a si mismo: {alias}')
            if alias in absorbed_uris:
                raise ValueError(f'[canonical_anchors] Alias legado duplicado como absorbido: {alias}')

    cycles = canonical_uris & absorbed_uris
    if cycles:
        raise ValueError(f'[canonical_anchors] Ciclo detectado en anchors: {sorted(cycles)}')
    return anchors


def build_anchor_mapping(anchors: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for anchor in anchors:
        canonical_uri = anchor['canonical_uri']
        for absorbed in anchor.get('absorbs', []):
            mapping[absorbed] = canonical_uri
    return mapping


def build_anchor_legacy_alias_mapping(anchors: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for anchor in anchors:
        canonical_uri = anchor['canonical_uri']
        for alias in anchor.get('legacy_aliases', []):
            mapping[alias] = canonical_uri
    return mapping


def apply_anchor_mapping(graph: Graph, anchor_mapping: dict[str, str]) -> tuple[Graph, dict[str, Any]]:
    rewritten = Graph()
    for prefix, namespace in graph.namespaces():
        rewritten.bind(prefix, namespace)
    rewritten_triples = 0
    rewritten_subjects = 0
    rewritten_objects = 0
    skipped_self_loops = 0

    for subject, predicate, obj in graph:
        new_subject = subject
        new_object = obj
        if isinstance(subject, URIRef) and str(subject) in anchor_mapping:
            new_subject = URIRef(anchor_mapping[str(subject)])
            if new_subject != subject:
                rewritten_subjects += 1
        if predicate != RDF.type and isinstance(obj, URIRef) and str(obj) in anchor_mapping:
            new_object = URIRef(anchor_mapping[str(obj)])
            if new_object != obj:
                rewritten_objects += 1
        if isinstance(new_object, URIRef) and new_subject == new_object and (new_subject != subject or new_object != obj):
            skipped_self_loops += 1
            continue
        if new_subject != subject or new_object != obj:
            rewritten_triples += 1
        rewritten.add((new_subject, predicate, new_object))

    return rewritten, {
        'anchor_absorbed_count': len(anchor_mapping),
        'anchor_rewritten_triples': rewritten_triples,
        'anchor_rewritten_subjects': rewritten_subjects,
        'anchor_rewritten_objects': rewritten_objects,
        'anchor_skipped_self_loops': skipped_self_loops,
        'anchor_mapping_applied': bool(anchor_mapping),
    }


def resolve_mapping_chain(initial_mapping: dict[str, str]) -> dict[str, str]:
    def resolve(uri: str) -> str:
        seen: set[str] = set()
        current = uri
        while current in initial_mapping and current not in seen:
            seen.add(current)
            current = initial_mapping[current]
        return current
    return {source: resolve(target) for source, target in initial_mapping.items()}


def merge_resolution_candidates(*candidate_sets: list) -> list:
    merged: dict[tuple[str, str, str], Any] = {}
    for candidate_list in candidate_sets:
        for candidate in candidate_list:
            key = (candidate.source_uri, candidate.candidate_uri, candidate.suggested_structural_issue)
            existing = merged.get(key)
            if existing is None:
                merged[key] = candidate
                continue
            existing.support_count = max(existing.support_count, candidate.support_count)
            existing.question_ids = sorted(set(existing.question_ids) | set(candidate.question_ids))
            existing.source_types = sorted(set(existing.source_types) | set(candidate.source_types))
            existing.candidate_types = sorted(set(existing.candidate_types) | set(candidate.candidate_types))
            existing.source_alignment_score = max(existing.source_alignment_score, candidate.source_alignment_score)
            existing.candidate_alignment_score = max(existing.candidate_alignment_score, candidate.candidate_alignment_score)
            existing.improvement_score = max(existing.improvement_score, candidate.improvement_score)
            existing.evidence = {**existing.evidence, **candidate.evidence}
            if existing.candidate_origin != candidate.candidate_origin:
                existing.candidate_origin = f"{existing.candidate_origin}+{candidate.candidate_origin}"
    return sorted(
        merged.values(),
        key=lambda item: (item.priority, -item.support_count, -item.improvement_score, -item.candidate_alignment_score, item.source_uri, item.candidate_uri),
    )


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
        if predicate != RDF.type and isinstance(obj, URIRef):
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
            if predicate == RDF.type:
                continue
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


def protect_declared_canonical_anchors(candidates: list, protected_uris: set[str]) -> tuple[list, int]:
    if not protected_uris:
        return candidates, 0
    filtered = [candidate for candidate in candidates if candidate.source_uri not in protected_uris]
    return filtered, len(candidates) - len(filtered)


def main() -> None:
    args = parse_args()
    raw_graph = load_graph(args.input)
    declared_anchors = load_canonical_anchors(args.canonical_anchors_path, graph=raw_graph)
    anchor_mapping = build_anchor_mapping(declared_anchors)
    legacy_alias_mapping = build_anchor_legacy_alias_mapping(declared_anchors)
    raw_graph, anchor_stats = apply_anchor_mapping(raw_graph, anchor_mapping)
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
    identifier_candidates = collect_identifier_based_candidates(raw_graph)
    surface_variant_diagnostics = collect_surface_variant_diagnostics(raw_graph)
    accepted_candidates = merge_resolution_candidates(
        identifier_candidates,
        diagnostics['accepted'],
        surface_variant_diagnostics['accepted'],
    )
    protected_anchor_uris = {anchor['canonical_uri'] for anchor in declared_anchors}
    accepted_candidates, protected_anchor_candidates_discarded = protect_declared_canonical_anchors(
        accepted_candidates,
        protected_anchor_uris,
    )
    clusters = group_resolution_candidates(accepted_candidates)
    selections = [select_canonical_entity(cluster, raw_graph) for cluster in clusters]

    resolution_payload = {
        'summary': {
            **diagnostics['summary'],
            'surface_variant_groups_inspected': surface_variant_diagnostics['summary']['surface_variant_groups_inspected'],
            'surface_variant_candidates_accepted': surface_variant_diagnostics['summary']['accepted_candidates'],
            'surface_variant_candidates_discarded': surface_variant_diagnostics['summary']['discarded_candidates'],
            'accepted_candidates': len(accepted_candidates),
            'discarded_candidates': len(diagnostics['discarded']) + len(surface_variant_diagnostics['discarded']),
            'candidate_origins': {
                'identifier_exact_match': len(identifier_candidates),
                'sandbox': diagnostics['summary'].get('candidate_origins', {}).get('sandbox', 0),
                'surface_variant_scan': surface_variant_diagnostics['summary'].get('candidate_origins', {}).get('surface_variant_scan', 0),
            },
            'protected_anchor_candidates_discarded': protected_anchor_candidates_discarded,
        },
        'results': candidates_to_jsonable(accepted_candidates),
        'discarded': diagnostics['discarded'] + surface_variant_diagnostics['discarded'],
    }
    write_json(args.resolution_candidates_path, resolution_payload)

    canonical_graph, rewrite_stats, entity_map = rewrite_graph(raw_graph, selections)
    for absorbed_uri, canonical_uri in anchor_mapping.items():
        entity_map[absorbed_uri] = {
            'canonical_uri': canonical_uri,
            'resolution_reason': 'declared_canonical_anchor',
            'entity_type': next((anchor.get('class', 'Unknown') for anchor in declared_anchors if absorbed_uri in anchor.get('absorbs', [])), 'Unknown'),
            'rules_applied': ['declared_canonical_anchor'],
            'support_question_ids': [],
            'supplemental_targets': [],
        }
    for alias_uri, canonical_uri in legacy_alias_mapping.items():
        entity_map[alias_uri] = {
            'canonical_uri': canonical_uri,
            'resolution_reason': 'declared_legacy_alias',
            'entity_type': next((anchor.get('class', 'Unknown') for anchor in declared_anchors if alias_uri in anchor.get('legacy_aliases', [])), 'Unknown'),
            'rules_applied': ['declared_legacy_alias'],
            'support_question_ids': [],
            'supplemental_targets': [],
        }
    tbox_graph = load_graph(OPERATIONAL_TBOX_PATH)
    mint_registry = load_mint_registry(ABOX_MINTED_ENTITY_REGISTRY_PATH)
    canonical_graph, sanitization_result = sanitize_abox_graph(
        canonical_graph,
        tbox_graph=tbox_graph,
        mint_registry=mint_registry,
    )
    semantic_validation = validate_abox_graph(
        canonical_graph,
        vocabulary=load_semantic_vocabulary(OPERATIONAL_TBOX_PATH),
    )
    save_mint_registry(mint_registry, ABOX_MINTED_ENTITY_REGISTRY_PATH)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canonical_graph.serialize(destination=args.output, format='turtle')
    write_json(args.entity_map_path, entity_map)

    report_payload = {
        'summary': {
            **rewrite_stats,
            **anchor_stats,
            'anchor_legacy_alias_count': len(legacy_alias_mapping),
            'sanitization': sanitization_result.to_manifest_summary(),
            'semantic_validation': semantic_validation.to_manifest_summary(),
            'input_path': str(args.input),
            'output_path': str(args.output),
            'resolution_candidates_path': str(args.resolution_candidates_path),
            'entity_map_path': str(args.entity_map_path),
            'surface_variant_groups_inspected': surface_variant_diagnostics['summary']['surface_variant_groups_inspected'],
            'surface_variant_candidates_accepted': surface_variant_diagnostics['summary']['accepted_candidates'],
            'surface_variant_candidates_discarded': surface_variant_diagnostics['summary']['discarded_candidates'],
            'identifier_exact_match_candidates': len(identifier_candidates),
            'protected_anchor_candidates_discarded': protected_anchor_candidates_discarded,
            'canonical_anchors_path': str(args.canonical_anchors_path),
        },
        'clusters_processed': clusters_to_jsonable(clusters),
        'selections': selections_to_jsonable(selections),
        'discarded_candidates': diagnostics['discarded'] + surface_variant_diagnostics['discarded'],
    }
    write_json(args.report_path, report_payload)

    print(f'[canonicalizer] Raw merged A-Box: {args.input}')
    print(f'[canonicalizer] Canonical operational A-Box: {args.output}')
    print(f'[canonicalizer] Accepted resolution candidates: {len(accepted_candidates)}')
    print(f'[canonicalizer] Declared anchor absorptions: {anchor_stats["anchor_absorbed_count"]}')
    print(f'[canonicalizer] Absorbed nodes: {rewrite_stats["absorbed_nodes_count"]}')
    print(f'[canonicalizer] Supplemental links added: {rewrite_stats["supplemental_links_added"]}')
    print(f'[canonicalizer] Canonical triples: {rewrite_stats["canonical_triples"]}')


if __name__ == '__main__':
    main()
