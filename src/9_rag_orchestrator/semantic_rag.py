import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RETRIEVAL_DIR = REPO_ROOT / 'src' / '8_retrieval'
if str(RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(RETRIEVAL_DIR))

import logging
import os
import sys
from dataclasses import asdict

from mistralai.client import Mistral
from rdflib import Graph
try:
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
except ModuleNotFoundError:
    def retry(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    def stop_after_attempt(*args, **kwargs):
        return None

    def wait_exponential(*args, **kwargs):
        return None

    def retry_if_exception_type(*args, **kwargs):
        return None

from artifact_contracts import MULTIHOP_DEBUG_REPORT_PATH, OPERATIONAL_ABOX_PATH, OPERATIONAL_TBOX_PATH, SCHEMA_CONDENSED_PATH
from text_to_sparql import append_query_debug_record, build_query_plan, execute_query_plan

logger = logging.getLogger(__name__)
TBOX_PATH = OPERATIONAL_TBOX_PATH
ABOX_PATH = OPERATIONAL_ABOX_PATH
MODEL = 'mistral-small-latest'


def cargar_grafo_memoria() -> Graph:
    if not TBOX_PATH.exists() or not ABOX_PATH.exists():
        print('Error: Missing T-Box or A-Box files.')
        sys.exit(1)
    graph = Graph()
    graph.parse(TBOX_PATH, format='turtle')
    graph.parse(ABOX_PATH, format='turtle')
    return graph


class MotorRAGSemantico:
    def __init__(self):
        api_key = os.environ.get('MISTRAL_API_KEY')
        if not api_key:
            print('Error: Variable MISTRAL_API_KEY not defined.')
            sys.exit(1)
        self.client = Mistral(api_key=api_key)
        logger.info('Loading operational graph...')
        self.grafo = cargar_grafo_memoria()
        self.esquema = self._cargar_esquema_condensado()
        logger.info(f'Graph loaded with {len(self.grafo)} triples.')

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda retry_state: print(f'Rate limit detected. Retrying LLM call (attempt {retry_state.attempt_number})...'),
    )
    def _llamada_llm_segura(self, mensajes: list) -> str:
        respuesta = self.client.chat.complete(model=MODEL, temperature=0.0, messages=mensajes)
        return respuesta.choices[0].message.content

    def _cargar_esquema_condensado(self) -> str:
        if not SCHEMA_CONDENSED_PATH.exists():
            return 'Not available.'
        return SCHEMA_CONDENSED_PATH.read_text(encoding='utf-8')

    def sintetizar_respuesta(self, pregunta: str, tripletas_crudas: list[tuple[str, str, str]]) -> str:
        contexto_str = '\n'.join([f'- {s} | {p} | {o}' for s, p, o in tripletas_crudas])
        prompt = (
            'You are the final assistant of a semantic RAG system. '
            'Answer using only the extracted graph context. '
            'If the context is insufficient, say so clearly.'
        )
        mensajes = [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': f'Question: {pregunta}\n\nExtracted graph context:\n{contexto_str}'},
        ]
        return self._llamada_llm_segura(mensajes)

    def consultar(self, pregunta: str):
        print('\n' + '=' * 50)
        print(f'USER: {pregunta}')
        print('=' * 50)
        print('\n1. Shared multi-hop planner working...')
        plan = build_query_plan(pregunta, self.esquema, self.grafo)
        execution = execute_query_plan(plan, self.grafo)
        print(f'   -> family={plan.plan_family} | template={plan.template_id} | hops={plan.predicted_hop_depth} | fallback={plan.fallback_used}')
        for trace in execution.trace.steps:
            print(f"   step={trace.step_id} mode={trace.mode} raw={trace.raw_result_count} out={trace.output_candidate_count} boundedness={trace.boundedness_status}")
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
            'trace': [asdict(step) for step in execution.trace.steps],
            'notes': 'semantic_rag_multihop',
        }, path=MULTIHOP_DEBUG_REPORT_PATH)
        print('3. Final synthesis running...')
        respuesta_final = self.sintetizar_respuesta(pregunta, execution.rows)
        print('\n' + '-' * 50)
        print('SEMANTIC RAG ANSWER:')
        print(respuesta_final)
        print('-' * 50 + '\n')
        return {
            'plan': asdict(plan),
            'trace': asdict(execution.trace),
            'tripletas': execution.rows,
            'respuesta': respuesta_final,
        }


if __name__ == '__main__':
    motor = MotorRAGSemantico()
    motor.consultar('What maintenance plan does the machine safety system require?')
