from __future__ import annotations

import argparse
import json
import os
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

from artifact_contracts import OPERATIONAL_ABOX_PATH, OPERATIONAL_TBOX_PATH, QUERY_DEBUG_REPORT_PATH, SCHEMA_CONDENSED_PATH
from text_to_sparql import build_query_plan, execute_query_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Interactive workbench for query planning over the operational graph.')
    parser.add_argument('question', help='Natural-language question to inspect.')
    parser.add_argument('--with-synthesis', action='store_true', help='Run final answer synthesis with Mistral if MISTRAL_API_KEY is available.')
    parser.add_argument('--max-rows', type=int, default=20, help='Maximum retrieved rows to print.')
    parser.add_argument('--save-debug', action='store_true', help='Append this run to query_debug_report.json.')
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


def estimate_hop_depth(plan) -> int:
    if plan.template_id in {'T1_literal_anchor', 'T6_purpose_lookup'}:
        return 1
    if plan.template_id in {'T2_reference_lookup', 'T3_regulatory_lookup', 'T4_component_attribute_lookup', 'T5_component_relation_lookup'}:
        return 2
    return 1


def maybe_synthesize(question: str, rows: list[tuple[str, str, str]]) -> str | None:
    if not rows:
        return '[EMPTY] No graph rows recovered.'
    api_key = os.environ.get('MISTRAL_API_KEY')
    if not api_key:
        return None
    try:
        from mistralai.client import Mistral
    except ModuleNotFoundError:
        return None
    client = Mistral(api_key=api_key)
    context = '\n'.join(f'- {s} | {p} | {o}' for s, p, o in rows)
    prompt = (
        'You are the final assistant of a semantic RAG system. '
        'Answer using only the extracted graph context. '
        'If the context is insufficient, say so clearly.'
    )
    response = client.chat.complete(
        model='mistral-small-latest',
        temperature=0.0,
        messages=[
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': f'Question: {question}\n\nGraph context:\n{context}'},
        ],
    )
    return response.choices[0].message.content


def main() -> None:
    args = parse_args()
    graph = load_graph()
    schema = load_schema()
    plan = build_query_plan(args.question, schema, graph)
    execution = execute_query_plan(plan, graph)
    output = {
        'question': args.question,
        'intent': plan.intent,
        'anchor_text': plan.anchor_text,
        'anchor_candidates': plan.anchor_candidates,
        'predicted_hop_depth': estimate_hop_depth(plan),
        'template_id': plan.template_id,
        'fallback_used': plan.fallback_used,
        'query_plan': asdict(plan),
        'result_count': len(execution.rows),
        'rows': execution.rows[: args.max_rows],
    }
    if args.with_synthesis:
        output['synthesized_answer'] = maybe_synthesize(args.question, execution.rows[: args.max_rows])
    if args.save_debug:
        payload = []
        if QUERY_DEBUG_REPORT_PATH.exists():
            try:
                payload = json.loads(QUERY_DEBUG_REPORT_PATH.read_text(encoding='utf-8'))
            except Exception:
                payload = []
        payload.append({
            'question': args.question,
            'intent': plan.intent,
            'anchor_text': plan.anchor_text,
            'anchor_candidates': plan.anchor_candidates,
            'predicted_hop_depth': estimate_hop_depth(plan),
            'template_id': plan.template_id,
            'fallback_used': plan.fallback_used,
            'result_count': len(execution.rows),
            'queries': [asdict(step) for step in plan.queries],
        })
        QUERY_DEBUG_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        QUERY_DEBUG_REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
