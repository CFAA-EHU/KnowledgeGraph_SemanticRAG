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
    MULTIHOP_DEBUG_REPORT_PATH,
    MULTIHOP_EVAL_REPORT_PATH,
    MULTIHOP_PLANNER_DECISION_REPORT_PATH,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
    QA_CANONICAL_PATH,
    QA_EVAL_REPORT_PATH,
    QA_FAILURE_ANALYSIS_PATH,
    QA_MULTIHOP_PATH,
    QUERY_DEBUG_REPORT_PATH,
    SCHEMA_CONDENSED_PATH,
)

RETRIEVAL_DIR = Path(__file__).resolve().parent
if str(RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(RETRIEVAL_DIR))

from text_to_sparql import append_query_debug_record, build_query_plan, execute_query_plan

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
    parser = argparse.ArgumentParser(description="Evaluate the operational runtime over canonical or multihop QA datasets.")
    parser.add_argument("--qa-file", type=Path, default=QA_CANONICAL_PATH, help="QA dataset to evaluate.")
    parser.add_argument("--report-path", type=Path, default=None, help="Detailed per-question report path.")
    parser.add_argument("--failure-analysis-path", type=Path, default=None, help="Aggregated analysis path.")
    parser.add_argument("--debug-report-path", type=Path, default=None, help="Query trace debug path.")
    parser.add_argument("--limit", type=int, default=0, help="Limit questions for quick runs.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Optional pause between questions.")
    return parser.parse_args()



def resolve_output_paths(qa_file: Path, report_path: Path | None, failure_analysis_path: Path | None, debug_report_path: Path | None) -> tuple[Path, Path, Path]:
    is_multihop = qa_file.resolve() == QA_MULTIHOP_PATH.resolve()
    resolved_report = report_path or (MULTIHOP_EVAL_REPORT_PATH if is_multihop else QA_EVAL_REPORT_PATH)
    resolved_failure = failure_analysis_path or (MULTIHOP_PLANNER_DECISION_REPORT_PATH if is_multihop else QA_FAILURE_ANALYSIS_PATH)
    resolved_debug = debug_report_path or (MULTIHOP_DEBUG_REPORT_PATH if is_multihop else QUERY_DEBUG_REPORT_PATH)
    return resolved_report, resolved_failure, resolved_debug



def cargar_grafo_memoria() -> Graph:
    if not TBOX_PATH.exists():
        raise SystemExit(f"Error: Missing T-Box at {TBOX_PATH}")
    if not ABOX_PATH.exists():
        raise SystemExit(f"Error: Missing A-Box at {ABOX_PATH}")
    graph = Graph()
    graph.parse(TBOX_PATH, format="turtle")
    graph.parse(ABOX_PATH, format="turtle")
    return graph


class EvaluadorRAG:
    def __init__(self, qa_file: Path, report_path: Path, failure_analysis_path: Path, debug_report_path: Path):
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise SystemExit("Error: Variable MISTRAL_API_KEY not defined.")
        self.qa_file = qa_file
        self.report_path = report_path
        self.failure_analysis_path = failure_analysis_path
        self.debug_report_path = debug_report_path
        self.client = Mistral(api_key=api_key)
        self.grafo = cargar_grafo_memoria()
        self.esquema = self._cargar_esquema_condensado()
        self.subject_uris = {str(subject) for subject in self.grafo.subjects() if isinstance(subject, URIRef)}

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=4, max=45),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda retry_state: print(f"Rate limit detected. Retrying LLM call (attempt {retry_state.attempt_number})..."),
    )
    def _llamada_llm_segura(self, mensajes: list) -> str:
        respuesta = self.client.chat.complete(model=MODEL, temperature=0.0, messages=mensajes)
        return respuesta.choices[0].message.content

    def _cargar_esquema_condensado(self) -> str:
        if not SCHEMA_CONDENSED_PATH.exists():
            return "Not available."
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
        payload = json.loads(self.qa_file.read_text(encoding="utf-8"))
        bank: list[dict] = []
        if isinstance(payload, list):
            for block_index, bloque in enumerate(payload):
                for question_index, item in enumerate(bloque.get("questions", [])):
                    bank.append({
                        "block_index": block_index,
                        "question_index": question_index,
                        "chunk_summary": bloque.get("chunk_summary"),
                        "question": item["question"],
                        "answer": item["answer"],
                        "expected_uris": item.get("expected_uris", []),
                        "source_dataset": item.get("source_dataset", bloque.get("source_dataset", self.qa_file.name)),
                        "reconciliation_label": item.get("reconciliation_label"),
                        "hop_depth": item.get("hop_depth"),
                        "expected_path": item.get("expected_path"),
                        "canonical_sparql_id": item.get("canonical_sparql_id"),
                    })
            return bank
        if isinstance(payload, dict):
            for question_index, item in enumerate(payload.get("questions", [])):
                bank.append({
                    "block_index": 0,
                    "question_index": question_index,
                    "chunk_summary": item.get("notes"),
                    "question": item["question"],
                    "answer": item.get("answer", item.get("notes", "")),
                    "expected_uris": item.get("expected_uris", []),
                    "source_dataset": self.qa_file.name,
                    "reconciliation_label": item.get("notes"),
                    "hop_depth": item.get("hop_depth"),
                    "expected_path": item.get("expected_path"),
                    "canonical_sparql_id": item.get("canonical_sparql_id"),
                })
            return bank
        raise ValueError("Unsupported QA dataset shape.")

    def sintetizar_respuesta(self, pregunta: str, tripletas_crudas: list[tuple[str, str, str]]) -> str:
        if not tripletas_crudas:
            return "[EMPTY] No graph relations were recovered for this question."
        contexto_str = "\n".join([f"- {s} | {p} | {o}" for s, p, o in tripletas_crudas])
        prompt = (
            "You are the final assistant of a semantic RAG system. "
            "Answer using only the extracted graph context. "
            "If the context is insufficient, say so clearly."
        )
        mensajes = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Question: {pregunta}\n\nExtracted graph context:\n{contexto_str}"},
        ]
        return self._llamada_llm_segura(mensajes)

    def _extraer_resultados(self, pregunta: str):
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
            obj_text = self._normalizar_uri(obj) if isinstance(obj, URIRef) else str(obj)
            fragmentos.append(f"{self._normalizar_uri(predicate)} {obj_text}")
        return self._normalizar_texto(" ".join(fragmentos))

    def _clasificar_pregunta(self, *, expected_uris: list[str], precision: float, recall: float, tripletas_limpias: list[tuple[str, str, str]], synthesized_answer: str, query_error: str | None, synthesis_error: str | None, question: str) -> str:
        if not expected_uris:
            return "golden_set_mismatch_or_ambiguity"
        if query_error:
            return "query_generation_failed"
        if synthesis_error:
            return "answer_synthesis_failed"
        answer_norm = self._normalizar_texto(synthesized_answer)
        negative_markers = ["[empty]", "no se encuentra", "no dispongo", "no hay informacion", "no se encontraron", "context is insufficient"]
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
        banco_preguntas = self._cargar_dataset()
        if limit > 0:
            banco_preguntas = banco_preguntas[:limit]
        self.debug_report_path.parent.mkdir(parents=True, exist_ok=True)
        self.debug_report_path.write_text("[]", encoding="utf-8")
        print(f"Starting evaluation of {len(banco_preguntas)} questions using {self.qa_file}...\n")
        resultados = []
        for index, item in enumerate(banco_preguntas, 1):
            pregunta = item["question"]
            expected_uris = item.get("expected_uris", [])
            execution = None
            query_plan = None
            tripletas_limpias: list[tuple[str, str, str]] = []
            uris_recuperadas = set()
            respuesta_final = ""
            query_error = None
            synthesis_error = None
            print("=" * 70)
            print(f"QUESTION {index}/{len(banco_preguntas)}: {pregunta}")
            print(f"EXPECTED: {item['answer']}")
            print("-" * 70)
            try:
                execution, tripletas_limpias, uris_recuperadas = self._extraer_resultados(pregunta)
                query_plan = execution.plan
                print(f"PLAN -> family={query_plan.plan_family} | template={query_plan.template_id} | hops={query_plan.predicted_hop_depth} | fallback={query_plan.fallback_used}")
                print(f"Recovered rows: {len(tripletas_limpias)}")
            except Exception as exc:
                query_error = str(exc)
                print(f"Error in query planning/execution: {query_error}")

            recovered_norm = {self._normalizar_uri(uri) for uri in uris_recuperadas if self._normalizar_uri(uri)}
            expected_norm = {self._normalizar_uri(uri) for uri in expected_uris if self._normalizar_uri(uri)}
            matching = recovered_norm.intersection(expected_norm)
            precision = len(matching) / len(recovered_norm) if recovered_norm else 0.0
            recall = len(matching) / len(expected_norm) if expected_norm else 0.0

            if query_error is None:
                try:
                    respuesta_final = self.sintetizar_respuesta(pregunta, tripletas_limpias)
                except Exception as exc:
                    synthesis_error = str(exc)
                    print(f"Error in synthesis: {synthesis_error}")

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

            if query_plan is not None and execution is not None:
                append_query_debug_record({
                    "question": pregunta,
                    "intent": query_plan.intent,
                    "plan_family": query_plan.plan_family,
                    "predicted_hop_depth": query_plan.predicted_hop_depth,
                    "anchor_text": query_plan.anchor_text,
                    "anchor_candidates": query_plan.anchor_candidates,
                    "template_id": query_plan.template_id,
                    "fallback_used": query_plan.fallback_used,
                    "trace": [asdict(step) for step in execution.trace.steps],
                    "notes": classification,
                }, path=self.debug_report_path)

            print(f"METRICS -> precision={precision:.2f} | recall={recall:.2f} | classification={classification}")
            print(f"ANSWER: {respuesta_final}")

            resultados.append({
                **item,
                "intent": query_plan.intent if query_plan else None,
                "plan_family": query_plan.plan_family if query_plan else None,
                "predicted_hop_depth": query_plan.predicted_hop_depth if query_plan else None,
                "template_id": query_plan.template_id if query_plan else None,
                "fallback_used": query_plan.fallback_used if query_plan else None,
                "anchor_text": query_plan.anchor_text if query_plan else None,
                "anchor_candidates": query_plan.anchor_candidates if query_plan else [],
                "queries": [asdict(step) for step in query_plan.steps] if query_plan else [],
                "trace": [asdict(step) for step in execution.trace.steps] if execution else [],
                "query_debug": query_plan.debug if query_plan else {},
                "sparql_query": query_plan.sparql if query_plan else "",
                "sparql_error": query_error,
                "retrieved_results": [list(row) for row in tripletas_limpias],
                "retrieved_uris": sorted(uris_recuperadas),
                "retrieved_uris_normalized": sorted(recovered_norm),
                "expected_uris_normalized": sorted(expected_norm),
                "matching_uris_normalized": sorted(matching),
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
            "plan_family_counts": dict(Counter(row["plan_family"] for row in resultados if row["plan_family"])),
            "hop_depth_counts": dict(Counter(str(row["predicted_hop_depth"]) for row in resultados if row["predicted_hop_depth"] is not None)),
            "fallback_count": sum(1 for row in resultados if row["fallback_used"]),
            "dataset_path": str(self.qa_file),
            "tbox_path": str(TBOX_PATH),
            "abox_path": str(ABOX_PATH),
            "schema_condensed_path": str(SCHEMA_CONDENSED_PATH),
            "debug_report_path": str(self.debug_report_path),
        }
        report = {"summary": metricas, "results": resultados}
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        failure_examples = []
        for category in ["graph_coverage_missing", "query_generation_failed", "query_too_broad_or_too_narrow", "answer_synthesis_failed", "naming_mismatch", "golden_set_mismatch_or_ambiguity"]:
            for row in resultados:
                if row["classification"] == category:
                    failure_examples.append({
                        "category": category,
                        "question": row["question"],
                        "plan_family": row["plan_family"],
                        "template_id": row["template_id"],
                        "predicted_hop_depth": row["predicted_hop_depth"],
                        "precision": row["precision"],
                        "recall": row["recall"],
                        "trace": row["trace"],
                    })
                    break

        ordered_failures = Counter(row["classification"] for row in resultados if row["classification"] != "ok").most_common()
        next_change = "planner_multi_hop"
        if ordered_failures:
            top_failure = ordered_failures[0][0]
            if top_failure == "answer_synthesis_failed":
                next_change = "answer_synthesis"
            elif top_failure == "graph_coverage_missing":
                next_change = "graph_modeling"
            elif top_failure == "query_too_broad_or_too_narrow":
                next_change = "boundedness_or_planner"

        failure_analysis = {
            "summary": metricas,
            "failure_distribution": dict(ordered_failures),
            "top_representative_questions": sorted(resultados, key=lambda row: (row["classification"] == "ok", row["recall"], row["precision"]))[:5],
            "failure_examples": failure_examples,
            "recommended_next_change": next_change,
        }
        self.failure_analysis_path.parent.mkdir(parents=True, exist_ok=True)
        self.failure_analysis_path.write_text(json.dumps(failure_analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        return report, failure_analysis


if __name__ == "__main__":
    args = parse_args()
    report_path, failure_path, debug_path = resolve_output_paths(args.qa_file, args.report_path, args.failure_analysis_path, args.debug_report_path)
    evaluador = EvaluadorRAG(args.qa_file, report_path, failure_path, debug_path)
    evaluador.ejecutar_evaluacion(limit=args.limit, sleep_seconds=args.sleep_seconds)
