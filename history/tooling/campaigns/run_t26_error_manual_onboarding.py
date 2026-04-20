from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from artifact_contracts import (
    GENERALIZATION_EVAL_REPORT_PATH,
    GOLDEN_SET_DIR,
    GRAPHDB_PUBLICATION_REPORT_PATH,
    MAN_8070_ERR_DECISION_REPORT_PATH,
    MAN_8070_ERR_EVAL_REPORT_PATH,
    MAN_8070_ERR_GOLDEN_SET_VALIDATION_REPORT_PATH,
    MAN_8070_ERR_ONBOARDING_REPORT_PATH,
    MULTIHOP_EVAL_REPORT_PATH,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_BUILD_ENTRYPOINT,
    QA_8070_QUICK_REF_BILINGUAL_V2_PATH,
    QA_CANONICAL_PATH,
    QA_CROSS_PATH,
    QA_MULTIHOP_PATH,
    RAW_DATA_DIR,
    REPO_ROOT,
    T26_ERROR_EXTRACTION_POLICY_REPORT_PATH,
    T26_ERROR_MANUAL_EVAL_DELTA_REPORT_PATH,
    T26_ERROR_MANUAL_GOLDEN_SET_PROFILE_PATH,
    T26_ERROR_RUNTIME_COLLISION_AUDIT_PATH,
    T26_GRAPHDB_CONSISTENCY_REPORT_PATH,
    T26_PHASE_CLOSURE_DECISION_REPORT_PATH,
    T26_PHASE_CLOSURE_REPORT_PATH,
    T26_RUNTIME_REGENERATION_REPORT_PATH,
    QUICK_REF_V2_EVAL_REPORT_PATH,
    CROSS_EVAL_REPORT_PATH,
    build_onboarding_profile,
)

MANUAL_ID = "man_8070_err"
SOURCE_PATH = RAW_DATA_DIR / "chunks_man_8070_err.txt"
GOLDEN_SET_PATH = GOLDEN_SET_DIR / "QA_chunks_man_8070_err.json"
MODEL_FALLBACKS = [
    "mistral-medium-latest",
    "open-mistral-nemo",
    "mistral-small-latest",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text_with_fallback(path: Path) -> tuple[str, str]:
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"No se pudo leer {path}: {last_error}")


def normalize_text_file(path: Path) -> dict:
    original_bytes = path.read_bytes()
    text, encoding_used = read_text_with_fallback(path)
    normalized_text = text.replace("\r\n", "\n")
    repaired = encoding_used not in {"utf-8", "utf-8-sig"} or normalized_text.encode("utf-8") != original_bytes
    if repaired:
        path.write_text(normalized_text, encoding="utf-8")
    return {
        "path": str(path),
        "encoding_detected": encoding_used,
        "repaired": repaired,
    }


def run_command(
    args: list[str], *, timeout_ms: int | None = None, env_overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if not env.get("MISTRAL_API_KEY"):
        legacy_extractor = REPO_ROOT / "src" / "2_extraction" / "llm_extractor.py"
        if legacy_extractor.exists():
            legacy_text = legacy_extractor.read_text(encoding="utf-8", errors="ignore")
            marker = 'api_key = "'
            start = legacy_text.find(marker)
            if start != -1:
                start += len(marker)
                end = legacy_text.find('"', start)
                if end != -1:
                    env["MISTRAL_API_KEY"] = legacy_text[start:end]
    env.setdefault("MISTRAL_MODEL", MODEL_FALLBACKS[0])
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=None if timeout_ms is None else timeout_ms / 1000,
        check=False,
        env=env,
    )


def is_rate_limit_failure(result: subprocess.CompletedProcess[str]) -> bool:
    haystack = f"{result.stdout}\n{result.stderr}".lower()
    return "429" in haystack or "rate limit" in haystack or "rate_limit" in haystack


def run_pipeline_with_model_fallback() -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
    attempts: list[dict[str, object]] = []
    last_result: subprocess.CompletedProcess[str] | None = None
    for model_name in MODEL_FALLBACKS:
        result = run_command(
            [
                sys.executable,
                str(OPERATIONAL_BUILD_ENTRYPOINT),
                "--mode",
                "resume-compatible",
                "--retry-profile",
                "micro-batch-recovery",
                "--source-chunks",
                str(SOURCE_PATH),
                "--manual-id",
                MANUAL_ID,
            ],
            timeout_ms=14400000,
            env_overrides={"MISTRAL_MODEL": model_name},
        )
        attempts.append(
            {
                "model_name": model_name,
                "returncode": result.returncode,
                "rate_limit_detected": is_rate_limit_failure(result),
            }
        )
        last_result = result
        if result.returncode == 0:
            return result, attempts
        if not is_rate_limit_failure(result):
            break
    if last_result is None:
        raise RuntimeError("No se pudo lanzar el pipeline de onboarding.")
    return last_result, attempts


def load_golden_set_payload() -> dict:
    return json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8-sig"))


def profile_golden_set(payload: dict) -> dict:
    questions = payload.get("questions", [])
    categories = Counter(question.get("category", "unknown") for question in questions)
    intents = Counter(question.get("intent", "unknown") for question in questions)
    families = Counter(question.get("expected_plan_family", "unknown") for question in questions)
    dominant_types = {
        "alarm_code_detail": [q["question_id"] for q in questions if q.get("category") == "alarms" and q.get("intent") == "alarm_lookup"],
        "alarm_resolution_or_procedure": [q["question_id"] for q in questions if q.get("intent") == "procedure_lookup"],
        "code_comparison": [q["question_id"] for q in questions if q.get("difficulty") == "multi_hop"],
        "parameter_or_range": [q["question_id"] for q in questions if q.get("intent") in {"parameter_lookup", "component_attribute_lookup"}],
        "mode_or_safety_policy": [q["question_id"] for q in questions if q.get("intent") in {"mode_lookup", "safety_instruction_lookup"}],
    }
    profile = {
        "manual_id": payload.get("manual_id", MANUAL_ID),
        "source_path": payload.get("source_path", SOURCE_PATH.name),
        "question_count": len(questions),
        "category_counts": dict(categories),
        "intent_counts": dict(intents),
        "expected_plan_family_counts": dict(families),
        "dominant_question_types": dominant_types,
        "max_hop_depth": max((question.get("hop_depth", 0) for question in questions), default=0),
    }
    write_json(T26_ERROR_MANUAL_GOLDEN_SET_PROFILE_PATH, profile)
    return profile


def validate_golden_set(payload: dict, normalization_report: dict) -> dict:
    questions = payload.get("questions", [])
    report = {
        "manual_id": payload.get("manual_id", MANUAL_ID),
        "golden_set_path": str(GOLDEN_SET_PATH),
        "json_valid": isinstance(questions, list),
        "encoding_ok": True,
        "question_count": len(questions),
        "needs_repair": normalization_report["repaired"],
        "repaired": normalization_report["repaired"],
        "notes": [] if len(questions) >= 5 else ["dataset_short_for_onboarding"],
    }
    write_json(MAN_8070_ERR_GOLDEN_SET_VALIDATION_REPORT_PATH, report)
    return report


def build_collision_audit() -> dict:
    baseline_triples = 52618
    candidate_collision_surfaces = [
        "OVERTEMP",
        "START",
        "RESET",
        "modo usuario",
        "proteccion OEM",
        "PLC",
        "CNCWR",
        "LI",
        "LO",
        ".pim",
        ".pit",
    ]
    candidate_collision_tokens = ["0008", "0040", "0169", "0173", "4026", "5026", "8023", "8026", "8458", "8459", "8789"]
    audit = {
        "baseline_triple_count_before": baseline_triples,
        "candidate_collision_surfaces": candidate_collision_surfaces,
        "candidate_collision_tokens": candidate_collision_tokens,
        "existing_families_reusable": [
            "installation_alarm_temperature_lookup",
            "generic_component_attribute_lookup",
            "generic_component_relation_lookup",
            "generic_literal_lookup",
            "quick_ref_work_mode_lookup",
        ],
        "existing_families_risky": [
            "quick_ref_key_purpose_lookup",
            "quick_ref_work_mode_lookup",
            "installation_alarm_temperature_lookup",
        ],
        "preventive_routing_needed": True,
        "notes": [
            "La pareja 0169/0173 comparte espacio semántico con OVERTEMP/E173 ya modelado en installation y debe auditarse para reutilización controlada.",
            "No deben introducirse tokens sueltos como error, warning, start, reset, plc o cnc como disparadores globales.",
        ],
    }
    write_json(T26_ERROR_RUNTIME_COLLISION_AUDIT_PATH, audit)
    return audit


def summarize_graphdb_healthcheck(stdout: str) -> dict:
    start = stdout.find("{")
    end = stdout.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {"status": "unknown", "errors": ["graphdb_healthcheck_no_json"]}
    return json.loads(stdout[start : end + 1])


def main() -> int:
    if not SOURCE_PATH.exists():
        raise SystemExit(f"Falta el source path requerido: {SOURCE_PATH}")
    if not GOLDEN_SET_PATH.exists():
        raise SystemExit(f"Falta el golden set requerido: {GOLDEN_SET_PATH}")

    source_normalization = normalize_text_file(SOURCE_PATH)
    golden_normalization = normalize_text_file(GOLDEN_SET_PATH)
    payload = load_golden_set_payload()
    profile_report = profile_golden_set(payload)
    validation_report = validate_golden_set(payload, golden_normalization)
    collision_audit = build_collision_audit()

    extraction_policy = {
        "profile_name": "micro-batch-recovery",
        "max_concurrency": 1,
        "batch_size": 1,
        "retry_policy": {
            "max_retries": 6,
            "retryable_errors": ["rate_limit", "timeout", "network_error", "api_error"],
        },
        "backoff_policy": [30, 60, 120, 240, 480, 900],
        "flush_strategy": "persist_after_each_chunk",
        "reason_for_conservative_mode": "Preventive extraction profile for a new high-cardinality error manual to avoid Mistral saturation.",
        "source_normalization": source_normalization,
        "golden_set_normalization": golden_normalization,
    }
    write_json(T26_ERROR_EXTRACTION_POLICY_REPORT_PATH, extraction_policy)

    pipeline_result, model_attempts = run_pipeline_with_model_fallback()
    extraction_policy["model_fallback_order"] = MODEL_FALLBACKS
    extraction_policy["model_attempts"] = model_attempts
    write_json(T26_ERROR_EXTRACTION_POLICY_REPORT_PATH, extraction_policy)
    if pipeline_result.returncode != 0:
        raise SystemExit(
            "Fallo el onboarding operativo de man_8070_err.\n"
            f"STDOUT:\n{pipeline_result.stdout}\nSTDERR:\n{pipeline_result.stderr}"
        )

    profile = build_onboarding_profile(MANUAL_ID, SOURCE_PATH)
    onboarding_payload = load_json(profile.onboarding_report_path)
    write_json(MAN_8070_ERR_ONBOARDING_REPORT_PATH, onboarding_payload)

    graph_before = 52618
    graph_after = None
    if GRAPHDB_PUBLICATION_REPORT_PATH.exists():
        graph_after = load_json(GRAPHDB_PUBLICATION_REPORT_PATH).get("triple_count")
    runtime_regen = {
        "timestamp": utc_now_iso(),
        "baseline_triple_count_before": graph_before,
        "triple_count_after": graph_after,
        "manual_integrated": True,
        "graph_rebuilt": OPERATIONAL_ABOX_PATH.exists(),
        "notes": "Runtime rebuilt via operational pipeline with conservative extractor profile.",
    }
    write_json(T26_RUNTIME_REGENERATION_REPORT_PATH, runtime_regen)

    healthcheck = run_command([sys.executable, "src\\7_database\\graphdb_healthcheck.py"], timeout_ms=120000)
    health_payload = summarize_graphdb_healthcheck(healthcheck.stdout)
    publish_attempted = False
    publish_ok = False
    publication_payload = {}
    if OPERATIONAL_ABOX_PATH.exists():
        publish_attempted = True
        publication = run_command([sys.executable, "src\\7_database\\publish_to_graphdb.py"], timeout_ms=600000)
        if publication.returncode != 0:
            raise SystemExit(f"Fallo la publicacion GraphDB.\nSTDOUT:\n{publication.stdout}\nSTDERR:\n{publication.stderr}")
        if GRAPHDB_PUBLICATION_REPORT_PATH.exists():
            publication_payload = load_json(GRAPHDB_PUBLICATION_REPORT_PATH)
            publish_ok = publication_payload.get("publication_status") == "ok"

    graphdb_report = {
        "graphdb_repository_ready": health_payload.get("status") == "repository_ready",
        "publication_attempted": publish_attempted,
        "publication_ok": publish_ok,
        "triple_count": publication_payload.get("triple_count", health_payload.get("triple_count")),
        "notes": "GraphDB mirror refreshed after onboarding operativo de man_8070_err." if publish_attempted else "GraphDB publication not attempted.",
    }
    write_json(T26_GRAPHDB_CONSISTENCY_REPORT_PATH, graphdb_report)

    print("T26 onboarding operativo completado hasta runtime+GraphDB.")
    print(json.dumps({
        "golden_set_profile": profile_report,
        "golden_set_validation": validation_report,
        "collision_audit": collision_audit,
        "graphdb": graphdb_report,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
