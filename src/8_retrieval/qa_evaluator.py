import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
import logging
import os
import re
import time
import unicodedata
from collections import Counter
from dataclasses import asdict
from statistics import mean

from mistralai.client import Mistral
from rdflib import Graph, URIRef
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

from artifact_contracts import (
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
    QA_CANONICAL_PATH,
    QA_EVAL_REPORT_PATH,
    QA_FAILURE_ANALYSIS_PATH,
    QUERY_DEBUG_REPORT_PATH,
    SCHEMA_CONDENSED_PATH,
)
RETRIEVAL_DIR = Path(__file__).resolve().parent
if str(RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(RETRIEVAL_DIR))

from text_to_sparql import (
    append_query_debug_record,
    build_query_plan,
    execute_query_plan,
)

logger = logging.getLogger(__name__)

TBOX_PATH = OPERATIONAL_TBOX_PATH
ABOX_PATH = OPERATIONAL_ABOX_PATH
MODEL = "mistral-small-latest"
STOPWORDS = {
    "de", "la", "el", "los", "las", "del", "para", "por", "que", "una", "uno", "segun", "sobre",
    "esta", "este", "estos", "estas", "cual", "donde", "quien", "como", "manual", "maquina",
    "indicado", "indicada", "mencionada", "respecto", "debe", "deben", "tipo", "informacion",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluacion del runtime operativo sobre el golden set canonico.")
    parser.add_argument("--qa-file", type=Path, default=QA_CANONICAL_PATH, help="Dataset QA canonico a evaluar.")
    parser.add_argument("--report-path", type=Path, default=QA_EVAL_REPORT_PATH, help="Reporte detallado por pregunta.")
    parser.add_argument("--failure-analysis-path", type=Path, default=QA_FAILURE_ANALYSIS_PATH, help="Analisis agregado de fallos.")
    parser.add_argument("--limit", type=int, default=0, help="Limita el numero de preguntas evaluadas para pruebas rapidas.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Pausa opcional entre preguntas.")
    return parser.parse_args()


def cargar_grafo_memoria() -> Graph:
    if not TBOX_PATH.exists():
        raise SystemExit(f"Error: No se encuentra T-Box en {TBOX_PATH}")
    if not ABOX_PATH.exists():
        raise SystemExit(f"Error: No se encuentra A-Box en {ABOX_PATH}")
    graph = Graph()
    graph.parse(TBOX_PATH, format="turtle")
    graph.parse(ABOX_PATH, format="turtle")
    return graph


class EvaluadorRAG:
    def __init__(self, qa_file: Path, report_path: Path, failure_analysis_path: Path):
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise SystemExit("Error: Variable MISTRAL_API_KEY no definida.")

        self.qa_file = qa_file
        self.report_path = report_path
        self.failure_analysis_path = failure_analysis_path
        self.client = Mistral(api_key=api_key)
        self.grafo = cargar_grafo_memoria()
        self.esquema = self._cargar_esquema_condensado()
        self.subject_uris = {str(subject) for subject in self.grafo.subjects() if isinstance(subject, URIRef)}

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=4, max=45),
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

    def _normalizar_uri(self, uri: str) -> str:
        if not uri:
            return ""
        return str(uri).split("/")[-1].split("#")[-1]

    def _normalizar_texto(self, text: str) -> str:
        text = unicodedata.normalize("NFKD", text or "")
        text = "".join(char for char in text if not unicodedata.combining(char))
        text = text.lower()
        text = re.sub(r"[^a-z0-9@/_-]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _tokenizar_pregunta(self, pregunta: str) -> list[str]:
        tokens = []
        for token in self._normalizar_texto(pregunta).split():
            if len(token) < 4 or token in STOPWORDS:
                continue
            tokens.append(token)
        return tokens

    def _cargar_dataset(self) -> list[dict]:
        with open(self.qa_file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            raise ValueError("El dataset QA canonico debe ser una lista de bloques.")
        return payload

    def sintetizar_respuesta(self, pregunta: str, tripletas_crudas: list[tuple[str, str, str]]) -> str:
        if not tripletas_crudas:
            return "[VACIO] No se encontraron relaciones en el grafo para esta pregunta."

        contexto_str = "\n".join([f"- {s} | {p} | {o}" for s, p, o in tripletas_crudas])
        prompt = """
        Eres el asistente de un sistema RAG semantico.
        Responde a la pregunta basandote UNICAMENTE en el contexto extraido.
        Redacta una respuesta directa y concisa.
        Si el contexto no permite responder, dilo claramente.
        """
        mensajes = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Pregunta: {pregunta}\n\nContexto extraido:\n{contexto_str}"},
        ]
        return self._llamada_llm_segura(mensajes)

    def _extraer_resultados(self, pregunta: str) -> tuple[object, list[tuple[str, str, str]], set[str]]:
        plan = build_query_plan(pregunta, self.esquema, self.grafo)
        execution = execute_query_plan(plan, self.grafo)
        uris_recuperadas = set()
        for fila in execution.raw_bindings:
            for value in fila:
                if isinstance(value, str) and value.startswith("http"):
                    uris_recuperadas.add(value)
        return execution, execution.rows, uris_recuperadas

    def _vecindario_uri(self, uri: str) -> str:
        fragmentos = []
        uri_ref = URIRef(uri)
        for _, predicate, obj in self.grafo.triples((uri_ref, None, None)):
            if isinstance(obj, URIRef):
                obj_text = self._normalizar_uri(obj)
            else:
                obj_text = str(obj)
            fragmentos.append(f"{self._normalizar_uri(predicate)} {obj_text}")
        return self._normalizar_texto(" ".join(fragmentos))

    def _clasificar_pregunta(
        self,
        *,
        expected_uris: list[str],
        precision: float,
        recall: float,
        tripletas_limpias: list[tuple[str, str, str]],
        synthesized_answer: str,
        query_error: str | None,
        synthesis_error: str | None,
        question: str,
    ) -> str:
        if not expected_uris:
            return "golden_set_mismatch_or_ambiguity"
        if query_error:
            return "query_generation_failed"
        if synthesis_error:
            return "answer_synthesis_failed"

        answer_norm = self._normalizar_texto(synthesized_answer)
        negative_markers = ["[vacio]", "no se encuentra", "no dispongo", "no hay informacion", "no se encontraron"]
        answer_is_negative = any(marker in answer_norm for marker in negative_markers)

        expected_exists = all(uri in self.subject_uris for uri in expected_uris)
        neighborhood = " ".join(self._vecindario_uri(uri) for uri in expected_uris if uri in self.subject_uris)
        question_tokens = self._tokenizar_pregunta(question)
        token_hits = sum(1 for token in question_tokens if token in neighborhood)

        if not expected_exists:
            return "graph_coverage_missing"
        if not tripletas_limpias:
            return "naming_mismatch" if token_hits == 0 else "query_too_broad_or_too_narrow"
        if answer_is_negative and recall > 0:
            return "answer_synthesis_failed"
        if precision == 0 and recall == 0:
            return "naming_mismatch" if token_hits == 0 else "query_too_broad_or_too_narrow"
        if recall == 1.0 and precision >= 0.05 and not answer_is_negative:
            return "ok"
        return "query_too_broad_or_too_narrow"

    def ejecutar_evaluacion(self, *, limit: int = 0, sleep_seconds: float = 0.0) -> tuple[dict, dict]:
        datos_qa = self._cargar_dataset()
        banco_preguntas = []
        for block_index, bloque in enumerate(datos_qa):
            for question_index, item in enumerate(bloque.get("questions", [])):
                banco_preguntas.append({
                    "block_index": block_index,
                    "question_index": question_index,
                    "chunk_summary": bloque.get("chunk_summary"),
                    "question": item["question"],
                    "answer": item["answer"],
                    "expected_uris": item.get("expected_uris", []),
                    "source_dataset": item.get("source_dataset", bloque.get("source_dataset", self.qa_file.name)),
                    "reconciliation_label": item.get("reconciliation_label"),
                })

        if limit > 0:
            banco_preguntas = banco_preguntas[:limit]

        QUERY_DEBUG_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        QUERY_DEBUG_REPORT_PATH.write_text("[]", encoding="utf-8")

        print(f"Iniciando evaluacion de {len(banco_preguntas)} preguntas usando {self.qa_file}...\n")
        resultados = []

        for index, item in enumerate(banco_preguntas, 1):
            pregunta = item["question"]
            respuesta_esperada = item["answer"]
            expected_uris = item.get("expected_uris", [])
            query_plan = None
            tripletas_limpias = []
            uris_recuperadas = set()
            respuesta_final = ""
            query_error = None
            synthesis_error = None

            print("=" * 70)
            print(f"PREGUNTA {index}/{len(banco_preguntas)}: {pregunta}")
            print(f"ESPERADA: {respuesta_esperada}")
            print("-" * 70)

            try:
                execution, tripletas_limpias, uris_recuperadas = self._extraer_resultados(pregunta)
                query_plan = execution.plan
                print(f"PLAN -> intent={query_plan.intent} | template={query_plan.template_id} | fallback={query_plan.fallback_used}")
                print("QUERY PRINCIPAL:\n" + query_plan.sparql)
                print(f"Resultados recuperados: {len(tripletas_limpias)}")
            except Exception as exc:
                query_error = str(exc)
                print(f"Error en query planning/exec: {query_error}")

            recovered_norm = {self._normalizar_uri(uri) for uri in uris_recuperadas if self._normalizar_uri(uri)}
            expected_norm = {self._normalizar_uri(uri) for uri in expected_uris if self._normalizar_uri(uri)}
            nodos_correctos = recovered_norm.intersection(expected_norm)
            precision = len(nodos_correctos) / len(recovered_norm) if recovered_norm else 0.0
            recall = len(nodos_correctos) / len(expected_norm) if expected_norm else 0.0

            if query_error is None:
                try:
                    respuesta_final = self.sintetizar_respuesta(pregunta, tripletas_limpias)
                except Exception as exc:
                    synthesis_error = str(exc)
                    print(f"Error en synthesis: {synthesis_error}")

            classification = self._clasificar_pregunta(
                expected_uris=expected_uris,
                precision=precision,
                recall=recall,
                tripletas_limpias=tripletas_limpias,
                synthesized_answer=respuesta_final,
                query_error=query_error,
                synthesis_error=synthesis_error,
                question=pregunta,
            )

            if query_plan is not None:
                append_query_debug_record({
                    "question": pregunta,
                    "intent": query_plan.intent,
                    "anchor_text": query_plan.anchor_text,
                    "anchor_candidates": query_plan.anchor_candidates,
                    "template_id": query_plan.template_id,
                    "candidate_count": query_plan.debug.get("candidate_count", 0),
                    "result_count": len(tripletas_limpias),
                    "fallback_used": query_plan.fallback_used,
                    "queries": [asdict(step) for step in query_plan.queries],
                    "notes": classification,
                })

            print(f"METRICAS -> Precision: {precision:.2f} | Recall: {recall:.2f} | Clasificacion: {classification}")
            print(f"SINTETIZADA: {respuesta_final}")

            resultados.append({
                **item,
                "intent": query_plan.intent if query_plan else None,
                "template_id": query_plan.template_id if query_plan else None,
                "fallback_used": query_plan.fallback_used if query_plan else None,
                "anchor_text": query_plan.anchor_text if query_plan else None,
                "anchor_candidates": query_plan.anchor_candidates if query_plan else [],
                "queries": [asdict(step) for step in query_plan.queries] if query_plan else [],
                "query_debug": query_plan.debug if query_plan else {},
                "sparql_query": query_plan.sparql if query_plan else "",
                "sparql_error": query_error,
                "retrieved_results": [list(row) for row in tripletas_limpias],
                "retrieved_uris": sorted(uris_recuperadas),
                "retrieved_uris_normalized": sorted(recovered_norm),
                "expected_uris_normalized": sorted(expected_norm),
                "matching_uris_normalized": sorted(nodos_correctos),
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "synthesized_answer": respuesta_final,
                "synthesis_error": synthesis_error,
                "classification": classification,
            })

            print("=" * 70 + "\n")
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        metricas = {
            "total_questions": len(resultados),
            "avg_precision": round(mean([row["precision"] for row in resultados]) if resultados else 0.0, 4),
            "avg_recall": round(mean([row["recall"] for row in resultados]) if resultados else 0.0, 4),
            "successful_questions": sum(1 for row in resultados if row["classification"] == "ok"),
            "classification_counts": dict(Counter(row["classification"] for row in resultados)),
            "intent_counts": dict(Counter(row["intent"] for row in resultados if row["intent"])),
            "fallback_count": sum(1 for row in resultados if row["fallback_used"]),
            "dataset_path": str(self.qa_file),
            "tbox_path": str(TBOX_PATH),
            "abox_path": str(ABOX_PATH),
            "schema_condensed_path": str(SCHEMA_CONDENSED_PATH),
            "query_debug_report_path": str(QUERY_DEBUG_REPORT_PATH),
        }
        report = {"summary": metricas, "results": resultados}
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        failure_examples = []
        for category in [
            "graph_coverage_missing",
            "query_generation_failed",
            "query_too_broad_or_too_narrow",
            "answer_synthesis_failed",
            "naming_mismatch",
            "golden_set_mismatch_or_ambiguity",
        ]:
            for row in resultados:
                if row["classification"] == category:
                    failure_examples.append({
                        "category": category,
                        "question": row["question"],
                        "intent": row["intent"],
                        "template_id": row["template_id"],
                        "fallback_used": row["fallback_used"],
                        "precision": row["precision"],
                        "recall": row["recall"],
                        "sparql_query": row["sparql_query"],
                        "retrieved_uris_normalized": row["retrieved_uris_normalized"][:10],
                        "expected_uris_normalized": row["expected_uris_normalized"],
                    })
                    break

        ordered_failures = Counter(row["classification"] for row in resultados if row["classification"] != "ok").most_common()
        next_change = "mejorar text_to_sparql"
        if ordered_failures:
            top_failure = ordered_failures[0][0]
            if top_failure == "naming_mismatch":
                next_change = "normalizar nombres entre preguntas y grafo"
            elif top_failure == "answer_synthesis_failed":
                next_change = "ajustar sintesis final"
            elif top_failure == "graph_coverage_missing":
                next_change = "completar cobertura factual del grafo"
            else:
                next_change = "mejorar text_to_sparql"

        failure_analysis = {
            "summary": metricas,
            "failure_distribution": dict(ordered_failures),
            "top_representative_questions": sorted(
                resultados,
                key=lambda row: (row["classification"] == "ok", row["recall"], row["precision"]),
            )[:5],
            "failure_examples": failure_examples,
            "recommended_next_change": next_change,
        }
        self.failure_analysis_path.parent.mkdir(parents=True, exist_ok=True)
        self.failure_analysis_path.write_text(json.dumps(failure_analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        return report, failure_analysis


if __name__ == "__main__":
    args = parse_args()
    evaluador = EvaluadorRAG(args.qa_file, args.report_path, args.failure_analysis_path)
    evaluador.ejecutar_evaluacion(limit=args.limit, sleep_seconds=args.sleep_seconds)
