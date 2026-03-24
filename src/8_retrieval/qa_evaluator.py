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
from difflib import SequenceMatcher
from statistics import mean

from rdflib import Graph, URIRef

from artifact_contracts import (
    BILINGUAL_DEBUG_REPORT_PATH,
    BILINGUAL_DECISION_REPORT_PATH,
    BILINGUAL_EVAL_REPORT_PATH,
    CANONICAL_ENTITY_MAP_PATH,
    CROSS_PLAN_CATALOG_PATH,
    CROSS_DEBUG_REPORT_PATH,
    CROSS_EVAL_REPORT_PATH,
    GENERALIZATION_EVAL_REPORT_PATH,
    MULTIHOP_DEBUG_REPORT_PATH,
    MULTIHOP_EVAL_REPORT_PATH,
    MULTIHOP_PLANNER_DECISION_REPORT_PATH,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
    PLANNER_GENERALIZATION_CATALOG_V2_PATH,
    QA_BILINGUAL_PATH,
    QA_CROSS_PATH,
    QA_CANONICAL_PATH,
    QA_8070_QUICK_REF_BILINGUAL_PATH,
    QA_8070_QUICK_REF_BILINGUAL_V2_PATH,
    QA_EVAL_REPORT_PATH,
    QA_FAILURE_ANALYSIS_PATH,
    QA_MULTIHOP_PATH,
    QUERY_DEBUG_REPORT_PATH,
    QUICK_REF_BILINGUAL_DEBUG_REPORT_PATH,
    QUICK_REF_BILINGUAL_EVAL_REPORT_PATH,
    QUICK_REF_INTEGRATION_DECISION_REPORT_PATH,
    QUICK_REF_V2_PLANNER_ALIGNMENT_REPORT_PATH,
    QUICK_REF_V2_DEBUG_REPORT_PATH,
    QUICK_REF_V2_EVAL_REPORT_PATH,
    SCHEMA_CONDENSED_PATH,
    SYNTHESIS_DEBUG_REPORT_PATH,
    SYNTHESIS_DECISION_REPORT_PATH,
    SYNTHESIS_EVAL_REPORT_PATH,
    SURFACE_POLISH_EVAL_REPORT_PATH,
    SURFACE_POLISH_DECISION_REPORT_PATH,
    T21_READINESS_DECISION_REPORT_PATH,
    T22_PLANNER_DECISION_REPORT_PATH,
    T22_PLANNER_EVAL_REPORT_PATH,
    CROSS_PLANNER_ALIGNMENT_REPORT_PATH,
)

RETRIEVAL_DIR = Path(__file__).resolve().parent
if str(RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(RETRIEVAL_DIR))

from synthesis_pipeline import append_synthesis_debug_record, synthesize_answer
from text_to_sparql import (
    append_query_debug_record,
    build_query_plan,
    execute_query_plan,
    export_cross_plan_catalog,
    export_planner_generalization_catalog_v2,
)

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


def _load_dataset_payload(qa_file: Path):
    return json.loads(qa_file.read_text(encoding="utf-8-sig"))


def _is_bilingual_payload(payload) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("pairs"), list)


def _path_equals(lhs: Path, rhs: Path) -> bool:
    return lhs.resolve() == rhs.resolve()


def _resolve_bilingual_mode(qa_file: Path, payload) -> str | None:
    if not _is_bilingual_payload(payload):
        return None
    if _path_equals(qa_file, QA_8070_QUICK_REF_BILINGUAL_V2_PATH):
        return "quick_ref_v2_mode"
    if _path_equals(qa_file, QA_CROSS_PATH):
        return "cross_manual_mode"
    if _path_equals(qa_file, QA_8070_QUICK_REF_BILINGUAL_PATH):
        return "quick_ref_mode"
    return "baseline_bilingual_mode"


def _default_decision_path_for_report(report_path: Path) -> Path:
    report_name = report_path.name
    if report_name.endswith("_eval_report.json"):
        return report_path.with_name(report_name.replace("_eval_report.json", "_decision_report.json"))
    if report_name.endswith("_report.json"):
        return report_path.with_name(report_name.replace("_report.json", "_decision_report.json"))
    return report_path.with_name(f"{report_path.stem}_decision.json")


def resolve_output_paths(qa_file: Path, report_path: Path | None, failure_analysis_path: Path | None, debug_report_path: Path | None) -> tuple[Path, Path, Path]:
    payload = _load_dataset_payload(qa_file)
    is_multihop = _path_equals(qa_file, QA_MULTIHOP_PATH)
    bilingual_mode = _resolve_bilingual_mode(qa_file, payload)
    is_bilingual = bilingual_mode is not None
    is_quick_ref_bilingual = bilingual_mode == "quick_ref_mode"
    is_quick_ref_v2 = bilingual_mode == "quick_ref_v2_mode"
    is_cross = bilingual_mode == "cross_manual_mode"
    resolved_report = report_path or (
        MULTIHOP_EVAL_REPORT_PATH
        if is_multihop
        else QUICK_REF_V2_EVAL_REPORT_PATH
        if is_quick_ref_v2
        else CROSS_EVAL_REPORT_PATH
        if is_cross
        else QUICK_REF_BILINGUAL_EVAL_REPORT_PATH
        if is_quick_ref_bilingual
        else BILINGUAL_EVAL_REPORT_PATH
        if is_bilingual
        else GENERALIZATION_EVAL_REPORT_PATH
        if qa_file.resolve() == QA_CANONICAL_PATH.resolve()
        else QA_EVAL_REPORT_PATH
    )
    resolved_failure = failure_analysis_path or (
        MULTIHOP_PLANNER_DECISION_REPORT_PATH
        if is_multihop
        else _default_decision_path_for_report(QUICK_REF_V2_EVAL_REPORT_PATH)
        if is_quick_ref_v2
        else _default_decision_path_for_report(CROSS_EVAL_REPORT_PATH)
        if is_cross
        else QUICK_REF_INTEGRATION_DECISION_REPORT_PATH
        if is_quick_ref_bilingual
        else BILINGUAL_DECISION_REPORT_PATH
        if is_bilingual
        else QA_FAILURE_ANALYSIS_PATH
    )
    resolved_debug = debug_report_path or (
        MULTIHOP_DEBUG_REPORT_PATH
        if is_multihop
        else QUICK_REF_V2_DEBUG_REPORT_PATH
        if is_quick_ref_v2
        else CROSS_DEBUG_REPORT_PATH
        if is_cross
        else QUICK_REF_BILINGUAL_DEBUG_REPORT_PATH
        if is_quick_ref_bilingual
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
        self.dataset_payload = _load_dataset_payload(self.qa_file)
        self.is_bilingual_dataset = _is_bilingual_payload(self.dataset_payload)
        self.bilingual_mode = _resolve_bilingual_mode(self.qa_file, self.dataset_payload)

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

    def _canonicalizar_respuesta_bilingue(self, text: str) -> str:
        normalized = self._normalizar_texto(text)
        replacements = [
            ("el manual indica", ""),
            ("the manual indicates", ""),
            ("las condiciones al entrar al modo", "the conditions when entering the mode"),
            ("punto de interrupcion", "interruption point"),
            ("historial de funciones g y m activas", "history of active g and m functions"),
            ("funciones g y m activas", "active g and m functions"),
            ("avance fijado por el oem", "feedrate set by the oem"),
            ("si no se define el avance", "if the feedrate is not defined"),
            ("movimiento de palpado", "probing movement"),
            ("mensaje de validacion", "validation message"),
            ("al pulsar start", "pressing the start key"),
            ("cambiar el atributo modificable", "change the modifiable attribute"),
            ("ficheros seleccionados", "selected files"),
            ("archivos", "files"),
            ("no puedan modificarse", "cannot be modified"),
            ("columna de atributos", "attributes column"),
            ("no hace falta seleccionar el bloque de parada", "there is no need to select the stop block"),
            ("bloque donde se interrumpio el programa", "block where the program was interrupted"),
            ("modelo de fresadora", "milling model"),
            ("longitud de las fresas", "length of the endmills"),
            ("herramientas de torno", "lathe tools"),
            ("modelo de torno en plano", "lathe model plane"),
            ("cualquier herramienta", "any tool"),
            ("tabla de utillajes", "fixture table"),
            ("decalajes de sujecion", "clamp offsets"),
            ("programa pieza", "part-program"),
            ("devuelve el entero mas uno", "returns the integer plus one"),
            ("el mismo numero si ya es entero", "the same number if it is already an integer"),
            ("operario", "operator"),
            ("panel de operador", "operator panel"),
            ("inspeccion de herramienta", "tool inspection"),
            ("menu vertical de softkeys", "vertical softkey menu"),
            ("selector set-up", "set-up selector"),
            ("apertura puertas", "doors"),
            ("no es necesario", "it is not necessary"),
            ("se paro por una emergencia", "was stopped due to an emergency"),
            ("tabla de parametros comunes", "common parameters table"),
            ("esta compartida entre todos los canales", "is shared across all channels"),
            ("la funcion", "the function"),
            ("funcion", "function"),
            ("la instruccion", "the instruction"),
            ("instruccion", "instruction"),
            ("la tecla", "the key"),
            ("tecla", "key"),
            ("se utiliza para", "is used for"),
            ("se usa para", "is used for"),
            ("sirve para mostrar", "is used to display"),
            ("mostrar la ayuda del cnc", "display cnc help"),
            ("ayuda del cnc", "cnc help"),
            ("arranca el husillo en sentido antihorario", "starts the spindle counterclockwise"),
            ("modo de bucle abierto", "open loop mode"),
            ("husillo maestro", "master spindle"),
            ("cero pieza", "part zero"),
            ("cinematica de la mesa", "table kinematics"),
            ("cinematica", "kinematics"),
            ("palpado", "probing"),
            ("hacer contacto", "making contact"),
            ("no hacer contacto", "not making contact"),
            ("decalajes de cero absolutos", "absolute zero offsets"),
            ("decalajes de cero", "zero offsets"),
            ("tabla de parametros comunes", "common parameters table"),
            ("parametros comunes", "common parameters"),
            ("todos los canales", "all channels"),
            ("busqueda de referencia", "home search"),
            ("plato divisor", "rotary table"),
            ("modo utilidades", "utilities mode"),
            ("borrar el programa", "erase the program"),
            ("borrar el programa", "erase the program"),
            ("simulacion de trayectoria teorica", "theoretical travel simulation"),
            ("trayectoria teorica", "theoretical travel"),
            ("plano principal", "main plane"),
            ("debe utilizarse", "should be used"),
            ("debe programarse", "must be programmed"),
            ("debe seleccionarse", "must be selected"),
            ("pulse", "press"),
        ]
        for source, target in replacements:
            normalized = normalized.replace(source, target)
        return re.sub(r"\s+", " ", normalized).strip()

    def _answer_match_mode(self, expected_answer: str, synthesized_answer: str) -> str:
        expected_norm = self._canonicalizar_respuesta_bilingue(expected_answer)
        answer_norm = self._canonicalizar_respuesta_bilingue(synthesized_answer)
        if not expected_norm:
            return "not_applicable"
        if not answer_norm:
            return "none"
        expected_tokens = {
            token
            for token in expected_norm.split()
            if len(token) >= 2 and token not in STOPWORDS
        }
        answer_tokens = {
            token
            for token in answer_norm.split()
            if len(token) >= 2 and token not in STOPWORDS
        }
        overlap = (
            len(expected_tokens.intersection(answer_tokens)) / len(expected_tokens)
            if expected_tokens
            else 0.0
        )
        ratio = SequenceMatcher(None, expected_norm, answer_norm).ratio()
        if expected_norm in answer_norm or answer_norm in expected_norm or ratio >= 0.92 or overlap >= 0.9:
            return "exact"
        if ratio >= 0.75 or overlap >= 0.7:
            return "high_partial"
        if ratio >= 0.45 or overlap >= 0.4:
            return "partial"
        if ratio >= 0.25 or overlap >= 0.2:
            return "weak"
        return "none"

    def _has_runner_blocker(self, result: dict) -> bool:
        return bool(result.get("sparql_error") or result.get("synthesis_error"))

    def _answer_match_sufficient(self, match_mode: str) -> bool:
        return match_mode in {"exact", "high_partial", "partial"}

    def _classify_cross_failure_cause(
        self,
        *,
        same_intent: bool,
        same_plan_family: bool,
        same_sparql_signature: bool,
        answer_language_ok: bool,
        es_result: dict,
        en_result: dict,
        es_match_mode: str,
        en_match_mode: str,
    ) -> str | None:
        if self._has_runner_blocker(es_result) or self._has_runner_blocker(en_result):
            return "benchmark_runner_blocker"
        if not all([same_intent, same_plan_family, same_sparql_signature, answer_language_ok]):
            return "cross_planner_gap"
        es_rows = len(es_result.get("retrieved_results", []))
        en_rows = len(en_result.get("retrieved_results", []))
        if es_rows == 0 and en_rows == 0:
            return "cross_document_coverage_gap"
        if not all([self._answer_match_sufficient(es_match_mode), self._answer_match_sufficient(en_match_mode)]):
            if es_rows > 0 or en_rows > 0:
                return "cross_surface_gap"
            return "cross_linking_gap"
        return None

    def _planner_failure_cause(self, row: dict) -> str | None:
        if row.get("has_runner_blocker"):
            return "benchmark_runner_blocker"
        if not row.get("same_anchor_resolution"):
            return "anchor_normalization_gap"
        if not row.get("same_plan_family"):
            return "family_selection_gap"
        if not row.get("same_sparql_signature"):
            return "sparql_convergence_gap"
        if self.bilingual_mode == "cross_manual_mode" and not row.get("cross_case_ok"):
            return "cross_family_missing"
        return None

    def _alignment_report_path_for_mode(self, mode: str | None) -> Path | None:
        if mode == "quick_ref_v2_mode":
            return QUICK_REF_V2_PLANNER_ALIGNMENT_REPORT_PATH
        if mode == "cross_manual_mode":
            return CROSS_PLANNER_ALIGNMENT_REPORT_PATH
        return None

    def _write_alignment_report(self, resultados: list[dict], mode: str | None) -> None:
        report_path = self._alignment_report_path_for_mode(mode)
        if report_path is None:
            return
        rows: list[dict] = []
        for pair in resultados:
            for question_language in ("es", "en"):
                question_result = pair["questions"][question_language]
                rows.append(
                    {
                        "case_id": pair["case_id"],
                        "question_language": question_language,
                        "normalized_question": question_result.get("normalized_question"),
                        "expected_pair_id": pair["case_id"],
                        "expected_plan_family": pair.get("expected_plan_family"),
                        "predicted_intent": question_result.get("intent"),
                        "predicted_anchor": question_result.get("anchor_text"),
                        "predicted_plan_family": question_result.get("plan_family"),
                        "sparql_signature": question_result.get("sparql_signature"),
                        "pair_alignment_status": "aligned" if pair.get("pair_alignment_ok") else "misaligned",
                        "failure_cause": self._planner_failure_cause(pair),
                    }
                )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_t22_summary_if_ready(self) -> None:
        required_paths = [
            GENERALIZATION_EVAL_REPORT_PATH,
            MULTIHOP_EVAL_REPORT_PATH,
            QUICK_REF_V2_EVAL_REPORT_PATH,
            CROSS_EVAL_REPORT_PATH,
        ]
        if not all(path.exists() for path in required_paths):
            return
        generalization = json.loads(GENERALIZATION_EVAL_REPORT_PATH.read_text(encoding="utf-8"))
        multihop = json.loads(MULTIHOP_EVAL_REPORT_PATH.read_text(encoding="utf-8"))
        quick_ref = json.loads(QUICK_REF_V2_EVAL_REPORT_PATH.read_text(encoding="utf-8"))
        cross = json.loads(CROSS_EVAL_REPORT_PATH.read_text(encoding="utf-8"))
        t21_decision = (
            json.loads(T21_READINESS_DECISION_REPORT_PATH.read_text(encoding="utf-8"))
            if T21_READINESS_DECISION_REPORT_PATH.exists()
            else {}
        )
        quick_summary = quick_ref.get("summary", {})
        cross_summary = cross.get("summary", {})
        baseline_ok = (
            generalization.get("summary", {}).get("successful_questions") == 13
            and multihop.get("summary", {}).get("successful_questions") == 7
        )
        quick_ok = all(
            [
                quick_summary.get("same_plan_family_count", 0) >= 18,
                quick_summary.get("same_sparql_signature_count", 0) >= 18,
                quick_summary.get("successful_pairs", 0) >= 18,
                quick_summary.get("answer_language_ok_count", 0) == quick_summary.get("total_pairs", 0) == 20,
            ]
        )
        cross_ok = all(
            [
                cross_summary.get("pair_alignment_ok_count", 0) >= 9,
                cross_summary.get("cross_case_ok_count", 0) >= 9,
                cross_summary.get("answer_language_ok_count", 0) == cross_summary.get("total_pairs", 0) == 11,
            ]
        )
        if baseline_ok and quick_ok and cross_ok:
            readiness = "ready_for_cleanup_and_next_manual"
        elif baseline_ok and (quick_ok or cross_ok):
            readiness = "ready_for_small_final_planner_follow_up"
        else:
            readiness = "not_ready_yet"
        planner_eval = {
            "baseline": {
                "generalization_successful_questions": generalization.get("summary", {}).get("successful_questions"),
                "multihop_successful_questions": multihop.get("summary", {}).get("successful_questions"),
                "baseline_ok": baseline_ok,
            },
            "quick_ref_v2": quick_summary,
            "cross_manual": cross_summary,
            "t21_baseline_decision": t21_decision,
        }
        planner_decision = {
            "readiness_state": readiness,
            "baseline_ok": baseline_ok,
            "quick_ref_gate_ok": quick_ok,
            "cross_gate_ok": cross_ok,
            "recommended_next_step": (
                "cleanup_and_next_manual"
                if readiness == "ready_for_cleanup_and_next_manual"
                else "small_final_planner_follow_up"
                if readiness == "ready_for_small_final_planner_follow_up"
                else "planner_hardening_continues"
            ),
        }
        T22_PLANNER_EVAL_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        T22_PLANNER_EVAL_REPORT_PATH.write_text(json.dumps(planner_eval, ensure_ascii=False, indent=2), encoding="utf-8")
        T22_PLANNER_DECISION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        T22_PLANNER_DECISION_REPORT_PATH.write_text(json.dumps(planner_decision, ensure_ascii=False, indent=2), encoding="utf-8")

    def _cargar_dataset(self) -> list[dict]:
        payload = self.dataset_payload
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
            expected_answer=item.get("answer", ""),
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

    def _clasificar_pregunta(self, *, expected_uris: list[str], expected_answer: str, precision: float, recall: float, tripletas_limpias: list[tuple[str, str, str]], synthesized_answer: str, query_error: str | None, synthesis_error: str | None, question: str) -> str:
        if not expected_uris:
            return "golden_set_mismatch_or_ambiguity"
        if query_error:
            return "query_generation_failed"
        if synthesis_error:
            return "answer_synthesis_failed"
        answer_norm = self._normalizar_texto(synthesized_answer)
        expected_answer_norm = self._normalizar_texto(expected_answer)
        negative_markers = ["[empty]", "no se encuentra", "no dispongo", "no hay informacion", "no se encontraron", "context is insufficient"]
        answer_is_negative = any(marker in answer_norm for marker in negative_markers)
        expected_answer_tokens = {
            token
            for token in expected_answer_norm.split()
            if len(token) >= 4 and token not in STOPWORDS
        }
        answer_tokens = {
            token
            for token in answer_norm.split()
            if len(token) >= 4 and token not in STOPWORDS
        }
        answer_overlap = (
            len(expected_answer_tokens.intersection(answer_tokens)) / len(expected_answer_tokens)
            if expected_answer_tokens
            else 0.0
        )
        strong_answer_match = bool(expected_answer_norm) and (
            expected_answer_norm in answer_norm
            or answer_norm in expected_answer_norm
            or answer_overlap >= 0.8
        )
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
        if strong_answer_match and not answer_is_negative:
            return "ok"
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
        mode = self.bilingual_mode or "baseline_bilingual_mode"
        if mode == "quick_ref_v2_mode":
            export_planner_generalization_catalog_v2()
        elif mode == "cross_manual_mode":
            export_cross_plan_catalog()
        print(f"Starting bilingual evaluation of {len(pares)} paired cases using {self.qa_file} [{mode}]...\n")

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
            es_answer_match_mode = self._answer_match_mode(pair.get("expected_answer", ""), es_result.get("synthesized_answer", ""))
            en_answer_match_mode = self._answer_match_mode(pair.get("expected_answer", ""), en_result.get("synthesized_answer", ""))
            has_runner_blocker = self._has_runner_blocker(es_result) or self._has_runner_blocker(en_result)
            pair_alignment_ok = all([same_intent, same_anchor_resolution, same_plan_family, same_sparql_signature, answer_language_ok])
            answer_match_ok = all([
                self._answer_match_sufficient(es_answer_match_mode),
                self._answer_match_sufficient(en_answer_match_mode),
            ])
            pair_ok = all([pair_alignment_ok, answer_match_ok, not has_runner_blocker])
            cross_case_ok = pair_ok
            dominant_failure_cause = self._classify_cross_failure_cause(
                same_intent=same_intent,
                same_plan_family=same_plan_family,
                same_sparql_signature=same_sparql_signature,
                answer_language_ok=answer_language_ok,
                es_result=es_result,
                en_result=en_result,
                es_match_mode=es_answer_match_mode,
                en_match_mode=en_answer_match_mode,
            )
            planner_failure_cause = self._planner_failure_cause({
                "has_runner_blocker": has_runner_blocker,
                "same_anchor_resolution": same_anchor_resolution,
                "same_plan_family": same_plan_family,
                "same_sparql_signature": same_sparql_signature,
                "cross_case_ok": cross_case_ok,
            })
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
                "es_answer_match_mode": es_answer_match_mode,
                "en_answer_match_mode": en_answer_match_mode,
                "has_runner_blocker": has_runner_blocker,
                "pair_alignment_ok": pair_alignment_ok,
                "pair_ok": pair_ok,
                "cross_case_ok": cross_case_ok,
                "dominant_failure_cause": dominant_failure_cause,
                "failure_cause": planner_failure_cause,
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
                f"answer_language_ok={answer_language_ok} | es_match={es_answer_match_mode} | "
                f"en_match={en_answer_match_mode} | blocker={has_runner_blocker}"
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        benchmark_runner_blocker_count = sum(1 for row in resultados if row["has_runner_blocker"])
        summary = {
            "total_pairs": len(resultados),
            "successful_pairs": sum(1 for row in resultados if row["pair_ok"]),
            "same_intent_count": sum(1 for row in resultados if row["same_intent"]),
            "same_anchor_resolution_count": sum(1 for row in resultados if row["same_anchor_resolution"]),
            "same_plan_family_count": sum(1 for row in resultados if row["same_plan_family"]),
            "same_sparql_signature_count": sum(1 for row in resultados if row["same_sparql_signature"]),
            "answer_language_ok_count": sum(1 for row in resultados if row["answer_language_ok"]),
            "pair_alignment_ok_count": sum(1 for row in resultados if row["pair_alignment_ok"]),
            "cross_case_ok_count": sum(1 for row in resultados if row["cross_case_ok"]),
            "benchmark_runner_blocker_count": benchmark_runner_blocker_count,
            "es_answer_match_mode_counts": dict(Counter(row["es_answer_match_mode"] for row in resultados)),
            "en_answer_match_mode_counts": dict(Counter(row["en_answer_match_mode"] for row in resultados)),
            "dominant_failure_cause_counts": dict(Counter(
                row["dominant_failure_cause"]
                for row in resultados
                if row.get("dominant_failure_cause")
            )),
            "bilingual_mode": mode,
            "dataset_path": str(self.qa_file),
            "abox_path": str(ABOX_PATH),
            "multilingual_runtime": True,
        }
        report = {"summary": summary, "results": resultados}
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.debug_report_path.write_text(json.dumps(debug_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_alignment_report(resultados, mode)

        if mode == "quick_ref_v2_mode":
            quick_ref_gate_solid = all([
                summary["answer_language_ok_count"] == summary["total_pairs"],
                summary["same_plan_family_count"] / summary["total_pairs"] >= 0.9 if summary["total_pairs"] else False,
                summary["same_sparql_signature_count"] / summary["total_pairs"] >= 0.9 if summary["total_pairs"] else False,
                summary["successful_pairs"] / summary["total_pairs"] >= 0.9 if summary["total_pairs"] else False,
                summary["benchmark_runner_blocker_count"] == 0,
            ])
            decision = {
                "summary": summary,
                "gate_name": "quick_ref_v2",
                "gate_status": "solid" if quick_ref_gate_solid else "not_solid",
                "failing_cases": [row["case_id"] for row in resultados if not row["pair_ok"]],
                "recommended_next_change": "promote_quick_ref_gate" if quick_ref_gate_solid else "lexical_surface_alignment",
            }
        elif mode == "cross_manual_mode":
            dominant_failure_cause = None
            if summary["dominant_failure_cause_counts"]:
                dominant_failure_cause = max(
                    summary["dominant_failure_cause_counts"].items(),
                    key=lambda item: item[1],
                )[0]
            cross_gate_reasonable = all([
                summary["pair_alignment_ok_count"] / summary["total_pairs"] >= 0.9 if summary["total_pairs"] else False,
                summary["cross_case_ok_count"] / summary["total_pairs"] >= 0.9 if summary["total_pairs"] else False,
                summary["benchmark_runner_blocker_count"] == 0,
                dominant_failure_cause not in {"benchmark_runner_blocker"},
            ])
            decision = {
                "summary": summary,
                "gate_name": "cross_manual",
                "gate_status": "reasonably_good" if cross_gate_reasonable else "below_threshold",
                "failing_cases": [row["case_id"] for row in resultados if not row["cross_case_ok"]],
                "dominant_failure_cause": dominant_failure_cause,
                "recommended_next_change": "promote_cross_gate" if cross_gate_reasonable else "cross_manual_follow_up",
            }
        else:
            decision = {
                "summary": summary,
                "gate_name": mode,
                "failing_cases": [row["case_id"] for row in resultados if not row["pair_ok"]],
                "recommended_next_change": "lexical_surface_alignment" if summary["successful_pairs"] < summary["total_pairs"] else "promote_bilingual_pairs",
            }
        self.failure_analysis_path.parent.mkdir(parents=True, exist_ok=True)
        self.failure_analysis_path.write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_t22_summary_if_ready()
        return report, decision

    def ejecutar_evaluacion(self, *, limit: int = 0, sleep_seconds: float = 0.0) -> tuple[dict, dict]:
        banco_preguntas = self._cargar_dataset()
        if self.is_bilingual_dataset:
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
                expected_answer=item.get("answer", ""),
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
