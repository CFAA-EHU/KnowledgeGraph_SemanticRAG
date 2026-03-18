from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
RETRIEVAL_DIR = REPO_ROOT / 'src' / '8_retrieval'
if str(RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(RETRIEVAL_DIR))

from rdflib import Graph

from artifact_contracts import MULTIHOP_DEBUG_REPORT_PATH, OPERATIONAL_ABOX_PATH, OPERATIONAL_TBOX_PATH, SCHEMA_CONDENSED_PATH, SYNTHESIS_DEBUG_REPORT_PATH
from synthesis_pipeline import append_synthesis_debug_record, synthesize_answer
from text_to_sparql import append_query_debug_record, build_query_plan, execute_query_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Interactive workbench for the shared multi-hop planner and synthesis layer.')
    parser.add_argument('question', help='Natural-language question to inspect.')
    parser.add_argument('--with-synthesis', action='store_true', help='Run the shared synthesis pipeline and show evidence selection, normalization and rendering.')
    parser.add_argument('--max-rows', type=int, default=20, help='Maximum retrieved rows to print.')
    parser.add_argument('--save-debug', action='store_true', help='Append this run to the debug reports.')
    return parser.parse_args()


def load_graph() -> Graph:
    graph = Graph()
    graph.parse(OPERATIONAL_TBOX_PATH, format='turtle')
    graph.parse(OPERATIONAL_ABOX_PATH, format='turtle')
    return graph


def load_schema() -> str:
    if not SCHEMA_CONDENSED_PATH.exists():
        return ''
    return SCHEMA_CONDENSED_PATH.read_text(encoding='utf-8')


def rows_for_synthesis(execution) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for row in execution.raw_bindings:
        if len(row) != 3:
            continue
        subject, predicate, obj = row
        subject_value = str(subject).split('/')[-1].split('#')[-1] if isinstance(subject, str) and str(subject).startswith('http') else str(subject)
        predicate_value = str(predicate).split('/')[-1].split('#')[-1] if isinstance(predicate, str) and str(predicate).startswith('http') else str(predicate)
        obj_value = str(obj).split('/')[-1].split('#')[-1] if isinstance(obj, str) and str(obj).startswith('http') else str(obj)
        rows.append((subject_value, predicate_value, obj_value))
    return rows


def provisional_gap(plan, execution, synthesis_trace: dict | None) -> str:
    if plan.final_boundedness in {'too_broad', 'too_narrow'}:
        return 'boundedness_gap'
    if not execution.rows:
        return 'graph_gap'
    if synthesis_trace and synthesis_trace.get('synthesis_category') not in {None, 'ok'}:
        return 'synthesis_gap'
    return 'planner_generalization_gap'


def main() -> None:
    args = parse_args()
    graph = load_graph()
    schema = load_schema()
    plan = build_query_plan(args.question, schema, graph)
    execution = execute_query_plan(plan, graph)
    synthesis_trace = None
    synthesized_answer = None
    if args.with_synthesis:
        synthesized_answer, synthesis_trace = synthesize_answer(args.question, rows_for_synthesis(execution)[: args.max_rows], plan)
        synthesis_trace = asdict(synthesis_trace)
    gap = provisional_gap(plan, execution, synthesis_trace)
    output = {
        'question': args.question,
        'intent': plan.intent,
        'plan_family': plan.plan_family,
        'anchor_text': plan.anchor_text,
        'anchor_candidates': plan.anchor_candidates,
        'predicted_hop_depth': plan.predicted_hop_depth,
        'template_id': plan.template_id,
        'fallback_used': plan.fallback_used,
        'confidence': plan.confidence,
        'recommended_action': plan.recommended_action,
        'final_boundedness': plan.final_boundedness,
        'provisional_gap': gap,
        'query_plan': asdict(plan),
        'trace': asdict(execution.trace),
        'result_count': len(execution.rows),
        'rows': execution.rows[: args.max_rows],
        'synthesis_trace': synthesis_trace,
        'synthesized_answer': synthesized_answer,
    }
    if args.save_debug:
        append_query_debug_record({
            'question': args.question,
            'intent': plan.intent,
            'plan_family': plan.plan_family,
            'predicted_hop_depth': plan.predicted_hop_depth,
            'anchor_text': plan.anchor_text,
            'anchor_candidates': plan.anchor_candidates,
            'template_id': plan.template_id,
            'fallback_used': plan.fallback_used,
            'confidence': plan.confidence,
            'recommended_action': plan.recommended_action,
            'final_boundedness': plan.final_boundedness,
            'provisional_gap': gap,
            'trace': [asdict(step) for step in execution.trace.steps],
            'result_count': len(execution.rows),
        }, path=MULTIHOP_DEBUG_REPORT_PATH)
        if synthesis_trace is not None:
            append_synthesis_debug_record({
                'question': args.question,
                'plan_family': plan.plan_family,
                'template_id': plan.template_id,
                'confidence': plan.confidence,
                'recommended_action': plan.recommended_action,
                'final_boundedness': plan.final_boundedness,
                'retrieved_results': [list(row) for row in execution.rows[: args.max_rows]],
                'synthesis_trace': synthesis_trace,
                'provisional_gap': gap,
            }, path=SYNTHESIS_DEBUG_REPORT_PATH)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
