import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
import logging
import re
import time
import unicodedata
from collections import Counter
from dataclasses import asdict
from statistics import mean

from rdflib import Graph, URIRef

from artifact_contracts import (
    BILINGUAL_DEBUG_REPORT_PATH,
    BILINGUAL_DECISION_REPORT_PATH,
    BILINGUAL_EVAL_REPORT_PATH,
    CANONICAL_ENTITY_MAP_PATH,
    GENERALIZATION_EVAL_REPORT_PATH,
    MULTIHOP_DEBUG_REPORT_PATH,
    MULTIHOP_EVAL_REPORT_PATH,
    MULTIHOP_PLANNER_DECISION_REPORT_PATH,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
    QA_BILINGUAL_PATH,
    QA_CANONICAL_PATH,
    QA_EVAL_REPORT_PATH,
    QA_FAILURE_ANALYSIS_PATH,
    QA_MULTIHOP_PATH,
    QUERY_DEBUG_REPORT_PATH,
    SCHEMA_CONDENSED_PATH,
    SYNTHESIS_DEBUG_REPORT_PATH,
    SYNTHESIS_DECISION_REPORT_PATH,
    SYNTHESIS_EVAL_REPORT_PATH,
    SURFACE_POLISH_EVAL_REPORT_PATH,
    SURFACE_POLISH_DECISION_REPORT_PATH,
)

RETRIEVAL_DIR = Path(__file__).resolve().parent
if str(RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(RETRIEVAL_DIR))

from synthesis_pipeline import append_synthesis_debug_record, synthesize_answer
from text_to_sparql import append_query_debug_record, build_query_plan, execute_query_plan

logger = logging.getLogger(__name__)
TBOX_PATH = OPERATIONAL_TBOX_PATH
ABOX_PATH = OPERATIONAL_ABOX_PATH
STOPWORDS = {
    "de", "la", "el", "los", "las", "del", "para", "por", "que", "una", "uno", "segun", "sobre",
    "esta", "este", "estos", "estas", "cual", "donde", "quien", "como", "manual", "maquina",
    "indicado", "indicada", "mencionada", "respecto", "debe", "deben", "tipo", "informacion",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the operational runtime over the linked operational A-Box and the formal QA datasets.")
    parser.add_argument("--qa-file", type=Path, default=QA_CANONICAL_PATH, help="QA dataset to evaluate.")
    parser.add_argument("--report-path", type=Path, default=None, help="Detailed per-question report path.")
    parser.add_argument("--failure-analysis-path", type=Path, default=None, help="Aggregated analysis path.")
    parser.add_argument("--debug-report-path", type=Path, default=None, help="Query trace debug path.")
    parser.add_argument("--limit", type=int, default=0, help="Limit questions for quick runs.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Optional pause between questions.")
    return parser.parse_args()


def resolve_output_paths(qa_file: Path, report_path: Path | None, failure_analysis_path: Path | None, debug_report_path: Path | None) -> tuple[Path, Path, Path]:
    is_multihop = qa_file.resolve() == QA_MULTIHOP_PATH.resolve()
    is_bilingual = qa_file.resolve() == QA_BILINGUAL_PATH.resolve()
    resolved_report = report_path or (
        MULTIHOP_EVAL_REPORT_PATH
        if is_multihop
        else BILINGUAL_EVAL_REPORT_PATH
        if is_bilingual
        else GENERALIZATION_EVAL_REPORT_PATH
        if qa_file.resolve() == QA_CANONICAL_PATH.resolve()
        else QA_EVAL_REPORT_PATH
    )
    resolved_failure = failure_analysis_path or (
        MULTIHOP_PLANNER_DECISION_REPORT_PATH
        if is_multihop
        else BILINGUAL_DECISION_REPORT_PATH
        if is_bilingual
        else QA_FAILURE_ANALYSIS_PATH
    )
    resolved_debug = debug_report_path or (
        MULTIHOP_DEBUG_REPORT_PATH
        if is_multihop
        else BILINGUAL_DEBUG_REPORT_PATH
        if is_bilingual
        else QUERY_DEBUG_REPORT_PATH
    )
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
        self.qa_file = qa_file
        self.report_path = report_path
        self.failure_analysis_path = failure_analysis_path
        self.debug_report_path = debug_report_path
        self.synthesis_eval_path = SYNTHESIS_EVAL_REPORT_PATH
        self.synthesis_debug_path = SYNTHESIS_DEBUG_REPORT_PATH
        self.synthesis_decision_path = SYNTHESIS_DECISION_REPORT_PATH
        self.surface_polish_eval_path = SURFACE_POLISH_EVAL_REPORT_PATH
        self.surface_polish_decision_path = SURFACE_POLISH_DECISION_REPORT_PATH
        self.grafo = cargar_grafo_memoria()
        self.esquema = self._cargar_esquema_condensado()
        self.subject_uris = {str(subject) for subject in self.grafo.subjects() if isinstance(subject, URIRef)}
        self.canonical_entity_map = self._cargar_canonical_entity_map()

    def _cargar_esquema_condensado(self) -> str:
        if not SCHEMA_CONDENSED_PATH.exists():
            return "Not available."
        return SCHEMA_CONDENSED_PATH.read_text(encoding="utf-8")

    def _cargar_canonical_entity_map(self) -> dict[str, dict]:
        if not CANONICAL_ENTITY_MAP_PATH.exists():
            return {}
        try:
            payload = json.loads(CANONICAL_ENTITY_MAP_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _canonicalize_expected_uris(self, uris: list[str]) -> list[str]:
        resolved: list[str] = []
        for uri in uris or []:
            canonical_uri = self.canonical_entity_map.get(uri, {}).get("canonical_uri", uri)
            if canonical_uri not in resolved:
                resolved.append(canonical_uri)
        return resolved

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
        if isinstance(payload, dict) and "pairs" in payload:
            return payload["pairs"]
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

    def _sparql_signature(self, plan) -> str:
        payload = {
            "plan_family": plan.plan_family,
            "template_id": plan.template_id,
            "steps": [asdict(step) for step in plan.steps],
        }
        return self._normalizar_texto(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def sintetizar_respuesta(self, pregunta: str, tripletas_crudas: list[tuple[str, str, str]], plan) -> tuple[str, dict]:
        respuesta, trace = synthesize_answer(pregunta, tripletas_crudas, plan)
        return respuesta, asdict(trace)

    def _rows_for_synthesis(self, execution) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for row in execution.raw_bindings:
            if len(row) != 3:
                continue
            subject, predicate, obj = row
            subject_value = self._normalizar_uri(subject) if isinstance(subject, str) and subject.startswith("http") else str(subject)
            predicate_value = self._normalizar_uri(predicate) if isinstance(predicate, str) and predicate.startswith("http") else str(predicate)
            obj_value = self._normalizar_uri(obj) if isinstance(obj, str) and obj.startswith("http") else str(obj)
            rows.append((subject_value, predicate_value, obj_value))
        return rows

    def _extraer_resultados(self, pregunta: str):
        plan = build_query_plan(pregunta, self.esquema, self.grafo)
        execution = execute_query_plan(plan, self.grafo)
        uris_recuperadas = set()
        for fila in execution.raw_bindings:
            for value in fila:
                if isinstance(value, str) and value.startswith("http"):
                    uris_recuperadas.add(value)
        return execution, execution.rows, self._rows_for_synthesis(execution), uris_recuperadas

    def _evaluar_pregunta(self, item: dict, debug_path: Path | None = None) -> dict:
        pregunta = item["question"]
        expected_uris_original = item.get("expected_uris", [])
        expected_uris = self._canonicalize_expected_uris(expected_uris_original)
        execution = None
        query_plan = None
        tripletas_limpias: list[tuple[str, str, str]] = []
        tripletas_sintesis: list[tuple[str, str, str]] = []
        uris_recuperadas = set()
        respuesta_final = ""
        synthesis_trace: dict = {}
        query_error = None
        synthesis_error = None

        try:
            execution, tripletas_limpias, tripletas_sintesis, uris_recuperadas = self._extraer_resultados(pregunta)
            query_plan = execution.plan
        except Exception as exc:
            query_error = str(exc)

        recovered_norm = {self._normalizar_uri(uri) for uri in uris_recuperadas if self._normalizar_uri(uri)}
        expected_norm = {self._normalizar_uri(uri) for uri in expected_uris if self._normalizar_uri(uri)}
        matching = recovered_norm.intersection(expected_norm)
        precision = len(matching) / len(recovered_norm) if recovered_norm else 0.0
        recall = len(matching) / len(expected_norm) if expected_norm else 0.0

        if query_error is None and query_plan is not None:
            try:
                respuesta_final, synthesis_trace = self.sintetizar_respuesta(pregunta, tripletas_sintesis, query_plan)
            except Exception as exc:
                synthesis_error = str(exc)

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

        if query_plan is not None and execution is not None and debug_path is not None:
            append_query_debug_record({
                "question": pregunta,
                "intent": query_plan.intent,
                "question_language": query_plan.question_language,
                "normalized_question": query_plan.normalized_question,
                "multilingual_lexicon_hits": query_plan.multilingual_lexicon_hits,
                "plan_family": query_plan.plan_family,
                "predicted_hop_depth": query_plan.predicted_hop_depth,
                "anchor_text": query_plan.anchor_text,
                "anchor_candidates": query_plan.anchor_candidates,
                "template_id": query_plan.template_id,
                "fallback_used": query_plan.fallback_used,
                "recommended_action": query_plan.recommended_action,
                "confidence": query_plan.confidence,
                "final_boundedness": query_plan.final_boundedness,
                "trace": [asdict(step) for step in execution.trace.steps],
                "notes": classification,
            }, path=debug_path)

        return {
            **item,
            "expected_uris_original": expected_uris_original,
            "expected_uris_canonicalized": expected_uris,
            "intent": query_plan.intent if query_plan else None,
            "question_language": query_plan.question_language if query_plan else None,
            "question_language_confidence": query_plan.question_language_confidence if query_plan else None,
            "normalized_question": query_plan.normalized_question if query_plan else None,
            "multilingual_lexicon_hits": query_plan.multilingual_lexicon_hits if query_plan else [],
            "answer_language": synthesis_trace.get("answer_language") if synthesis_trace else None,
            "plan_family": query_plan.plan_family if query_plan else None,
            "predicted_hop_depth": query_plan.predicted_hop_depth if query_plan else None,
            "template_id": query_plan.template_id if query_plan else None,
            "fallback_used": query_plan.fallback_used if query_plan else None,
            "recommended_action": query_plan.recommended_action if query_plan else None,
            "confidence": query_plan.confidence if query_plan else {},
            "final_boundedness": query_plan.final_boundedness if query_plan else None,
            "anchor_text": query_plan.anchor_text if query_plan else None,
            "anchor_candidates": query_plan.anchor_candidates if query_plan else [],
            "queries": [asdict(step) for step in query_plan.steps] if query_plan else [],
            "trace": [asdict(step) for step in execution.trace.steps] if execution else [],
            "query_debug": query_plan.debug if query_plan else {},
            "sparql_query": query_plan.sparql if query_plan else "",
            "sparql_signature": self._sparql_signature(query_plan) if query_plan else "",
            "sparql_error": query_error,
            "retrieved_results": [list(row) for row in tripletas_limpias],
            "retrieved_uris": sorted(uris_recuperadas),
            "retrieved_uris_normalized": sorted(recovered_norm),
            "expected_uris_normalized": sorted(expected_norm),
            "matching_uris_normalized": sorted(matching),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "synthesized_answer": respuesta_final,
            "synthesis_trace": synthesis_trace,
            "synthesis_error": synthesis_error,
            "classification": classification,
        }

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

    def _build_synthesis_summary(self, resultados: list[dict]) -> dict:
        categories = Counter(row.get("synthesis_trace", {}).get("synthesis_category") for row in resultados if row.get("synthesis_trace"))
        answer_modes = Counter(row.get("synthesis_trace", {}).get("answer_mode") for row in resultados if row.get("synthesis_trace"))
        return {
            "summary": {
                "total_questions": len(resultados),
                "synthesis_category_counts": dict(categories),
                "answer_mode_counts": dict(answer_modes),
                "questions_with_selected_evidence": sum(1 for row in resultados if row.get("synthesis_trace", {}).get("selected_evidence")),
                "questions_with_surface_normalization": sum(1 for row in resultados if "surface_normalized" in row.get("synthesis_trace", {}).get("notes", [])),
            },
            "results": [
                {
                    "question": row["question"],
                    "classification": row["classification"],
                    "plan_family": row.get("plan_family"),
                    "answer_mode": row.get("synthesis_trace", {}).get("answer_mode"),
                    "selected_evidence": row.get("synthesis_trace", {}).get("selected_evidence", []),
                    "normalized_values": row.get("synthesis_trace", {}).get("normalized_values", []),
                    "pre_polish_answer": row.get("synthesis_trace", {}).get("pre_polish_answer"),
                    "rendered_answer": row.get("synthesized_answer"),
                    "applied_surface_rules": row.get("synthesis_trace", {}).get("applied_surface_rules", []),
                    "synthesis_category": row.get("synthesis_trace", {}).get("synthesis_category"),
                    "notes": row.get("synthesis_trace", {}).get("notes", []),
                }
                for row in resultados
            ],
        }

    def _build_synthesis_decision(self, resultados: list[dict], metricas: dict) -> dict:
        category_counter = Counter(row.get("synthesis_trace", {}).get("synthesis_category") for row in resultados if row.get("synthesis_trace"))
        category_counter.pop("ok", None)
        next_change = "value_surface_polish_minor"
        if category_counter:
            top_category = category_counter.most_common(1)[0][0]
            mapping = {
                "wrong_value_prioritization": "post_retrieval_ranking",
                "redundant_answer": "response_rendering",
                "literal_formatting_issue": "value_normalization",
                "answer_under-specified": "evidence_selection",
                "answer_over-specified": "response_rendering",
                "naming_surface_issue": "value_normalization",
            }
            next_change = mapping.get(top_category, "value_surface_polish_minor")
        return {
            "summary": metricas,
            "residual_synthesis_categories": dict(category_counter),
            "top_examples": [
                {
                    "question": row["question"],
                    "plan_family": row.get("plan_family"),
                    "synthesis_category": row.get("synthesis_trace", {}).get("synthesis_category"),
                    "notes": row.get("synthesis_trace", {}).get("notes", []),
                    "rendered_answer": row.get("synthesized_answer"),
                }
                for row in resultados[:5]
            ],
            "recommended_next_change": next_change,
        }

    def _ejecutar_evaluacion_bilingue(self, pares: list[dict], *, limit: int = 0, sleep_seconds: float = 0.0) -> tuple[dict, dict]:
        if limit > 0:
            pares = pares[:limit]
        self.debug_report_path.parent.mkdir(parents=True, exist_ok=True)
        self.debug_report_path.write_text("[]", encoding="utf-8")
        print(f"Starting bilingual evaluation of {len(pares)} paired cases using {self.qa_file}...\n")

        resultados: list[dict] = []
        debug_rows: list[dict] = []
        for index, pair in enumerate(pares, 1):
            case_id = pair["case_id"]
            print("=" * 70)
            print(f"PAIR {index}/{len(pares)}: {case_id}")
            print("-" * 70)
            es_result = self._evaluar_pregunta(
                {
                    "question": pair["questions"]["es"],
                    "answer": pair.get("expected_answer", ""),
                    "expected_uris": pair.get("expected_uris", []),
                    "case_id": case_id,
                    "category": pair.get("category"),
                    "expected_plan_family": pair.get("expected_plan_family"),
                    "question_variant": "es",
                },
                debug_path=self.debug_report_path,
            )
            en_result = self._evaluar_pregunta(
                {
                    "question": pair["questions"]["en"],
                    "answer": pair.get("expected_answer", ""),
                    "expected_uris": pair.get("expected_uris", []),
                    "case_id": case_id,
                    "category": pair.get("category"),
                    "expected_plan_family": pair.get("expected_plan_family"),
                    "question_variant": "en",
                },
                debug_path=self.debug_report_path,
            )
            same_intent = es_result.get("intent") == en_result.get("intent")
            same_plan_family = es_result.get("plan_family") == en_result.get("plan_family") == pair.get("expected_plan_family")
            same_sparql_signature = es_result.get("sparql_signature") == en_result.get("sparql_signature") and bool(es_result.get("sparql_signature"))
            same_anchor_resolution = (
                es_result.get("anchor_text") == en_result.get("anchor_text")
                or set(es_result.get("matching_uris_normalized", [])) == set(en_result.get("matching_uris_normalized", []))
            )
            answer_language_ok = es_result.get("answer_language") == "es" and en_result.get("answer_language") == "en"
            pair_ok = all([same_intent, same_plan_family, same_sparql_signature, answer_language_ok])
            result_row = {
                "case_id": case_id,
                "category": pair.get("category"),
                "expected_plan_family": pair.get("expected_plan_family"),
                "expected_uris": pair.get("expected_uris", []),
                "same_intent": same_intent,
                "same_anchor_resolution": same_anchor_resolution,
                "same_plan_family": same_plan_family,
                "same_sparql_signature": same_sparql_signature,
                "answer_language_ok": answer_language_ok,
                "pair_ok": pair_ok,
                "questions": {
                    "es": es_result,
                    "en": en_result,
                },
            }
            resultados.append(result_row)
            debug_rows.append(result_row)
            print(
                f"same_intent={same_intent} | same_anchor={same_anchor_resolution} | "
                f"same_plan_family={same_plan_family} | same_sparql={same_sparql_signature} | "
                f"answer_language_ok={answer_language_ok}"
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        summary = {
            "total_pairs": len(resultados),
            "successful_pairs": sum(1 for row in resultados if row["pair_ok"]),
            "same_intent_count": sum(1 for row in resultados if row["same_intent"]),
            "same_anchor_resolution_count": sum(1 for row in resultados if row["same_anchor_resolution"]),
            "same_plan_family_count": sum(1 for row in resultados if row["same_plan_family"]),
            "same_sparql_signature_count": sum(1 for row in resultados if row["same_sparql_signature"]),
            "answer_language_ok_count": sum(1 for row in resultados if row["answer_language_ok"]),
            "dataset_path": str(self.qa_file),
            "abox_path": str(ABOX_PATH),
            "multilingual_runtime": True,
        }
        report = {"summary": summary, "results": resultados}
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.debug_report_path.write_text(json.dumps(debug_rows, ensure_ascii=False, indent=2), encoding="utf-8")

        decision = {
            "summary": summary,
            "failing_cases": [row["case_id"] for row in resultados if not row["pair_ok"]],
            "recommended_next_change": "lexical_surface_alignment" if summary["successful_pairs"] < summary["total_pairs"] else "promote_bilingual_pairs",
        }
        self.failure_analysis_path.parent.mkdir(parents=True, exist_ok=True)
        self.failure_analysis_path.write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")
        return report, decision

    def ejecutar_evaluacion(self, *, limit: int = 0, sleep_seconds: float = 0.0) -> tuple[dict, dict]:
        banco_preguntas = self._cargar_dataset()
        if self.qa_file.resolve() == QA_BILINGUAL_PATH.resolve():
            return self._ejecutar_evaluacion_bilingue(banco_preguntas, limit=limit, sleep_seconds=sleep_seconds)
        if limit > 0:
            banco_preguntas = banco_preguntas[:limit]
        self.debug_report_path.parent.mkdir(parents=True, exist_ok=True)
        self.debug_report_path.write_text("[]", encoding="utf-8")
        self.synthesis_debug_path.parent.mkdir(parents=True, exist_ok=True)
        self.synthesis_debug_path.write_text("[]", encoding="utf-8")
        print(f"Starting evaluation of {len(banco_preguntas)} questions using {self.qa_file}...\n")
        resultados = []
        for index, item in enumerate(banco_preguntas, 1):
            pregunta = item["question"]
            expected_uris_original = item.get("expected_uris", [])
            expected_uris = self._canonicalize_expected_uris(expected_uris_original)
            execution = None
            query_plan = None
            tripletas_limpias: list[tuple[str, str, str]] = []
            tripletas_sintesis: list[tuple[str, str, str]] = []
            uris_recuperadas = set()
            respuesta_final = ""
            synthesis_trace: dict = {}
            query_error = None
            synthesis_error = None
            print("=" * 70)
            print(f"QUESTION {index}/{len(banco_preguntas)}: {pregunta}")
            print(f"EXPECTED: {item['answer']}")
            print("-" * 70)
            try:
                execution, tripletas_limpias, tripletas_sintesis, uris_recuperadas = self._extraer_resultados(pregunta)
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

            if query_error is None and query_plan is not None:
                try:
                    respuesta_final, synthesis_trace = self.sintetizar_respuesta(pregunta, tripletas_sintesis, query_plan)
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
                    "question_language": query_plan.question_language,
                    "question_language_confidence": query_plan.question_language_confidence,
                    "normalized_question": query_plan.normalized_question,
                    "multilingual_lexicon_hits": query_plan.multilingual_lexicon_hits,
                    "plan_family": query_plan.plan_family,
                    "predicted_hop_depth": query_plan.predicted_hop_depth,
                    "anchor_text": query_plan.anchor_text,
                    "anchor_candidates": query_plan.anchor_candidates,
                    "template_id": query_plan.template_id,
                    "fallback_used": query_plan.fallback_used,
                    "recommended_action": query_plan.recommended_action,
                    "confidence": query_plan.confidence,
                    "final_boundedness": query_plan.final_boundedness,
                    "trace": [asdict(step) for step in execution.trace.steps],
                    "notes": classification,
                }, path=self.debug_report_path)
                append_synthesis_debug_record({
                    "question": pregunta,
                    "intent": query_plan.intent,
                    "question_language": query_plan.question_language,
                    "answer_language": synthesis_trace.get("answer_language"),
                    "normalized_question": query_plan.normalized_question,
                    "plan_family": query_plan.plan_family,
                    "template_id": query_plan.template_id,
                    "recommended_action": query_plan.recommended_action,
                    "confidence": query_plan.confidence,
                    "final_boundedness": query_plan.final_boundedness,
                    "retrieved_results": [list(row) for row in tripletas_limpias],
                    "synthesis_trace": synthesis_trace,
                    "classification": classification,
                }, path=self.synthesis_debug_path)

            print(f"METRICS -> precision={precision:.2f} | recall={recall:.2f} | classification={classification}")
            print(f"ANSWER: {respuesta_final}")

            resultados.append({
                **item,
                "expected_uris_original": expected_uris_original,
                "expected_uris_canonicalized": expected_uris,
                "intent": query_plan.intent if query_plan else None,
                "question_language": query_plan.question_language if query_plan else None,
                "question_language_confidence": query_plan.question_language_confidence if query_plan else None,
                "normalized_question": query_plan.normalized_question if query_plan else None,
                "multilingual_lexicon_hits": query_plan.multilingual_lexicon_hits if query_plan else [],
                "answer_language": synthesis_trace.get("answer_language") if synthesis_trace else None,
                "plan_family": query_plan.plan_family if query_plan else None,
                "predicted_hop_depth": query_plan.predicted_hop_depth if query_plan else None,
                "template_id": query_plan.template_id if query_plan else None,
                "fallback_used": query_plan.fallback_used if query_plan else None,
                "recommended_action": query_plan.recommended_action if query_plan else None,
                "confidence": query_plan.confidence if query_plan else {},
                "final_boundedness": query_plan.final_boundedness if query_plan else None,
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
                "synthesis_trace": synthesis_trace,
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
            "boundedness_counts": dict(Counter(row["final_boundedness"] for row in resultados if row.get("final_boundedness"))),
            "avg_plan_confidence": round(mean([row.get("confidence", {}).get("overall", 0.0) for row in resultados]) if resultados else 0.0, 4),
            "fallback_count": sum(1 for row in resultados if row["fallback_used"]),
            "dataset_path": str(self.qa_file),
            "tbox_path": str(TBOX_PATH),
            "abox_path": str(ABOX_PATH),
            "schema_condensed_path": str(SCHEMA_CONDENSED_PATH),
            "debug_report_path": str(self.debug_report_path),
            "synthesis_debug_report_path": str(self.synthesis_debug_path),
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
                        "synthesis_trace": row.get("synthesis_trace", {}),
                    })
                    break

        ordered_failures = Counter(row["classification"] for row in resultados if row["classification"] != "ok").most_common()
        next_change = "answer_synthesis"
        if ordered_failures:
            top_failure = ordered_failures[0][0]
            if top_failure == "graph_coverage_missing":
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

        synthesis_eval = self._build_synthesis_summary(resultados)
        self.synthesis_eval_path.parent.mkdir(parents=True, exist_ok=True)
        self.synthesis_eval_path.write_text(json.dumps(synthesis_eval, ensure_ascii=False, indent=2), encoding="utf-8")
        self.surface_polish_eval_path.parent.mkdir(parents=True, exist_ok=True)
        self.surface_polish_eval_path.write_text(json.dumps(synthesis_eval, ensure_ascii=False, indent=2), encoding="utf-8")

        synthesis_decision = self._build_synthesis_decision(resultados, metricas)
        self.synthesis_decision_path.parent.mkdir(parents=True, exist_ok=True)
        self.synthesis_decision_path.write_text(json.dumps(synthesis_decision, ensure_ascii=False, indent=2), encoding="utf-8")
        self.surface_polish_decision_path.parent.mkdir(parents=True, exist_ok=True)
        self.surface_polish_decision_path.write_text(json.dumps(synthesis_decision, ensure_ascii=False, indent=2), encoding="utf-8")
        return report, failure_analysis


if __name__ == "__main__":
    args = parse_args()
    report_path, failure_path, debug_path = resolve_output_paths(args.qa_file, args.report_path, args.failure_analysis_path, args.debug_report_path)
    evaluador = EvaluadorRAG(args.qa_file, report_path, failure_path, debug_path)
    evaluador.ejecutar_evaluacion(limit=args.limit, sleep_seconds=args.sleep_seconds)
