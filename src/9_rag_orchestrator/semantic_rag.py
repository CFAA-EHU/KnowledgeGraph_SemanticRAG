import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RETRIEVAL_DIR = REPO_ROOT / 'src' / '8_retrieval'
if str(RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(RETRIEVAL_DIR))

import logging
import sys
from dataclasses import asdict

from rdflib import Graph

from artifact_contracts import MULTIHOP_DEBUG_REPORT_PATH, OPERATIONAL_ABOX_PATH, OPERATIONAL_TBOX_PATH, SCHEMA_CONDENSED_PATH, SYNTHESIS_DEBUG_REPORT_PATH
from synthesis_pipeline import append_synthesis_debug_record, synthesize_answer
from text_to_sparql import append_query_debug_record, build_query_plan, execute_query_plan

logger = logging.getLogger(__name__)
TBOX_PATH = OPERATIONAL_TBOX_PATH
ABOX_PATH = OPERATIONAL_ABOX_PATH


def cargar_grafo_memoria() -> Graph:
    if not TBOX_PATH.exists() or not ABOX_PATH.exists():
        print('Error: Missing T-Box or A-Box files.')
        sys.exit(1)
    graph = Graph()
    graph.parse(TBOX_PATH, format='turtle')
    graph.parse(ABOX_PATH, format='turtle')
    return graph


def _rows_for_synthesis(execution) -> list[tuple[str, str, str]]:
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


class MotorRAGSemantico:
    def __init__(self):
        logger.info('Loading operational graph...')
        self.grafo = cargar_grafo_memoria()
        self.esquema = self._cargar_esquema_condensado()
        logger.info(f'Graph loaded with {len(self.grafo)} triples.')

    def _cargar_esquema_condensado(self) -> str:
        if not SCHEMA_CONDENSED_PATH.exists():
            return 'Not available.'
        return SCHEMA_CONDENSED_PATH.read_text(encoding='utf-8')

    def sintetizar_respuesta(self, pregunta: str, tripletas_crudas: list[tuple[str, str, str]], plan) -> tuple[str, dict]:
        answer, trace = synthesize_answer(pregunta, tripletas_crudas, plan)
        return answer, asdict(trace)

    def consultar(self, pregunta: str):
        print('\n' + '=' * 50)
        print(f'USER: {pregunta}')
        print('=' * 50)
        print('\n1. Shared multi-hop planner working...')
        plan = build_query_plan(pregunta, self.esquema, self.grafo)
        execution = execute_query_plan(plan, self.grafo)
        print(f'   -> family={plan.plan_family} | template={plan.template_id} | hops={plan.predicted_hop_depth} | fallback={plan.fallback_used}')
        print(f"   -> confidence={plan.confidence.get('overall', 0.0):.2f} | recommended_action={plan.recommended_action}")
        for trace in execution.trace.steps:
            print(f"   step={trace.step_id} mode={trace.mode} raw={trace.raw_result_count} out={trace.output_candidate_count} boundedness={trace.boundedness_status} prune_reason={trace.prune_reason}")
        print('2. Graph retrieval complete...')
        print(f'   -> Recovered {len(execution.rows)} semantic rows.')
        append_query_debug_record({
            'question': pregunta,
            'intent': plan.intent,
            'plan_family': plan.plan_family,
            'predicted_hop_depth': plan.predicted_hop_depth,
            'anchor_text': plan.anchor_text,
            'anchor_candidates': plan.anchor_candidates,
            'template_id': plan.template_id,
            'fallback_used': plan.fallback_used,
            'recommended_action': plan.recommended_action,
            'confidence': plan.confidence,
            'final_boundedness': plan.final_boundedness,
            'trace': [asdict(step) for step in execution.trace.steps],
            'notes': 'semantic_rag_multihop',
        }, path=MULTIHOP_DEBUG_REPORT_PATH)
        print('3. Synthesis pipeline working...')
        respuesta_final, synthesis_trace = self.sintetizar_respuesta(pregunta, _rows_for_synthesis(execution), plan)
        print(f"   -> answer_mode={synthesis_trace.get('answer_mode')} | synthesis_category={synthesis_trace.get('synthesis_category')}")
        print(f"   -> selected_evidence={len(synthesis_trace.get('selected_evidence', []))} | normalized_values={len(synthesis_trace.get('normalized_values', []))}")
        append_synthesis_debug_record({
            'question': pregunta,
            'plan_family': plan.plan_family,
            'template_id': plan.template_id,
            'confidence': plan.confidence,
            'recommended_action': plan.recommended_action,
            'final_boundedness': plan.final_boundedness,
            'retrieved_results': [list(row) for row in execution.rows],
            'synthesis_trace': synthesis_trace,
            'notes': 'semantic_rag_runtime',
        }, path=SYNTHESIS_DEBUG_REPORT_PATH)
        print('\n' + '-' * 50)
        print('SEMANTIC RAG ANSWER:')
        print(respuesta_final)
        print('-' * 50 + '\n')
        return {
            'plan': asdict(plan),
            'trace': asdict(execution.trace),
            'tripletas': execution.rows,
            'synthesis_trace': synthesis_trace,
            'respuesta': respuesta_final,
        }


if __name__ == '__main__':
    motor = MotorRAGSemantico()
    motor.consultar('What maintenance plan does the machine safety system require?')
