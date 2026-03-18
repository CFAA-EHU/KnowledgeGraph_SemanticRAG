import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RETRIEVAL_DIR = REPO_ROOT / "src" / "8_retrieval"
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

from artifact_contracts import OPERATIONAL_ABOX_PATH, OPERATIONAL_TBOX_PATH, QUERY_DEBUG_REPORT_PATH, SCHEMA_CONDENSED_PATH
from text_to_sparql import append_query_debug_record, build_query_plan, execute_query_plan

logger = logging.getLogger(__name__)

TBOX_PATH = OPERATIONAL_TBOX_PATH
ABOX_PATH = OPERATIONAL_ABOX_PATH
MODEL = "mistral-small-latest"


def cargar_grafo_memoria() -> Graph:
    if not TBOX_PATH.exists() or not ABOX_PATH.exists():
        print("Error: Faltan archivos T-Box o A-Box.")
        sys.exit(1)
    g = Graph()
    g.parse(TBOX_PATH, format="turtle")
    g.parse(ABOX_PATH, format="turtle")
    return g


class MotorRAGSemantico:
    def __init__(self):
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            print("Error: Variable MISTRAL_API_KEY no definida.")
            sys.exit(1)

        self.client = Mistral(api_key=api_key)
        logger.info("Cargando Grafo de Conocimiento (T-Box + A-Box)...")
        self.grafo = cargar_grafo_memoria()
        self.esquema = self._cargar_esquema_condensado()
        logger.info(f"Grafo inicializado con {len(self.grafo)} tripletas.")

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda retry_state: print(f"Rate limit detectado. Reintentando llamada al LLM (intento {retry_state.attempt_number})..."),
    )
    def _llamada_llm_segura(self, mensajes: list) -> str:
        respuesta = self.client.chat.complete(model=MODEL, temperature=0.0, messages=mensajes)
        return respuesta.choices[0].message.content

    def _cargar_esquema_condensado(self) -> str:
        if not SCHEMA_CONDENSED_PATH.exists():
            return "No disponible."
        return SCHEMA_CONDENSED_PATH.read_text(encoding="utf-8")

    def sintetizar_respuesta(self, pregunta: str, tripletas_crudas: list[tuple[str, str, str]]) -> str:
        contexto_str = "\n".join([f"- {s} | {p} | {o}" for s, p, o in tripletas_crudas])

        prompt = """
        Eres el asistente final de un sistema RAG semantico.
        Tu tarea es responder a la pregunta del usuario utilizando UNICAMENTE la informacion proporcionada en el contexto extraido del grafo.
        - Si el contexto esta vacio o no contiene la respuesta, di claramente "No dispongo de informacion en la base de datos para responder a esto."
        - No inventes informacion externa.
        - Redacta una respuesta natural, directa y concisa.
        """

        mensajes = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Pregunta: {pregunta}\n\nContexto extraido del grafo:\n{contexto_str}"},
        ]

        return self._llamada_llm_segura(mensajes)

    def consultar(self, pregunta: str):
        print("\n" + "=" * 50)
        print(f"USUARIO: {pregunta}")
        print("=" * 50)

        print("\n1. Query layer compartido trabajando...")
        plan = build_query_plan(pregunta, self.esquema, self.grafo)
        print(f"   -> intent={plan.intent} | template={plan.template_id} | fallback={plan.fallback_used}")

        print("2. Ejecutando busqueda en el grafo...")
        execution = execute_query_plan(plan, self.grafo)
        tripletas_limpias = execution.rows
        print(f"   -> Se recuperaron {len(tripletas_limpias)} relaciones semanticas.")

        append_query_debug_record({
            "question": pregunta,
            "intent": plan.intent,
            "anchor_text": plan.anchor_text,
            "anchor_candidates": plan.anchor_candidates,
            "template_id": plan.template_id,
            "candidate_count": plan.debug.get("candidate_count", 0),
            "result_count": len(tripletas_limpias),
            "fallback_used": plan.fallback_used,
            "queries": [asdict(step) for step in plan.queries],
            "notes": "semantic_rag",
        }, path=QUERY_DEBUG_REPORT_PATH)

        print("3. Agente de sintesis redactando respuesta...")
        respuesta_final = self.sintetizar_respuesta(pregunta, tripletas_limpias)

        print("\n" + "-" * 50)
        print("RESPUESTA RAG SEMANTICO:")
        print(respuesta_final)
        print("-" * 50 + "\n")
        return {
            "plan": asdict(plan),
            "tripletas": tripletas_limpias,
            "respuesta": respuesta_final,
        }


if __name__ == "__main__":
    motor = MotorRAGSemantico()
    motor.consultar("Para que sirve el manual de la brochadora A218 / RASHEM - 7x3000x500?")
