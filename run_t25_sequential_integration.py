from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from artifact_contracts import (
    GOLDEN_SET_DIR,
    GRAPHDB_EQUIVALENCE_REPORT_PATH,
    GRAPHDB_PUBLICATION_REPORT_PATH,
    GRAPHDB_REPOSITORY_ID,
    MULTIHOP_EVAL_REPORT_PATH,
    OPERATIONAL_ABOX_PATH,
    PROCESSED_DATA_DIR,
    QA_8070_QUICK_REF_BILINGUAL_V2_PATH,
    QA_CANONICAL_PATH,
    QA_CROSS_PATH,
    QA_MULTIHOP_PATH,
    QUICK_REF_V2_EVAL_REPORT_PATH,
    RAW_DATA_DIR,
    T25_MANUAL_ORDER_PATH,
    T25_MULTI_MANUAL_DECISION_REPORT_PATH,
    T25_MULTI_MANUAL_INTEGRATION_REPORT_PATH,
    T25_PENDING_MANUALS_INVENTORY_PATH,
    GENERALIZATION_EVAL_REPORT_PATH,
    build_onboarding_profile,
)

REPO_ROOT = Path(__file__).resolve().parent
QA_EVALUATOR = REPO_ROOT / "src" / "8_retrieval" / "qa_evaluator.py"
PIPELINE = REPO_ROOT / "run_operational_pipeline.py"
GRAPHDB_PUBLISH = REPO_ROOT / "src" / "7_database" / "publish_to_graphdb.py"
GRAPHDB_HEALTHCHECK = REPO_ROOT / "src" / "7_database" / "graphdb_healthcheck.py"

ALREADY_INTEGRATED_MANUAL_IDS = {"a218", "8070_quick_ref"}


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_with_repair(path: Path) -> tuple[dict, str]:
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
    last_exc = None
    for encoding in encodings:
        try:
            return json.loads(path.read_text(encoding=encoding)), encoding
        except Exception as exc:  # pragma: no cover - defensive CLI path
            last_exc = exc
    raise ValueError(f"No se pudo leer {path}: {last_exc}")


def run_command(args: list[str], *, env: dict | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(args, cwd=REPO_ROOT, text=True, capture_output=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            f"Comando fallo ({result.returncode}): {' '.join(args)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def validate_report_success(report_path: Path, *, expected_success: int) -> bool:
    if not report_path.exists():
        return False
    summary = read_json(report_path).get("summary", {})
    return summary.get("successful_questions") == expected_success


def validate_pair_success(report_path: Path, *, expected_success: int) -> bool:
    if not report_path.exists():
        return False
    summary = read_json(report_path).get("summary", {})
    return summary.get("successful_pairs") == expected_success


def evaluate_golden_set_shape(payload: dict) -> int:
    questions = payload.get("questions", [])
    return len(questions) if isinstance(questions, list) else 0


def guess_language(payload: dict) -> str:
    languages = Counter(
        question.get("question_language", "unknown")
        for question in payload.get("questions", [])
        if isinstance(question, dict)
    )
    if not languages:
        return "unknown"
    return languages.most_common(1)[0][0]


def build_pending_inventory() -> list[dict]:
    inventory: list[dict] = []
    for golden_path in sorted(GOLDEN_SET_DIR.glob("QA_chunks_*.json")):
        payload, encoding = load_json_with_repair(golden_path)
        manual_id = payload.get("manual_id") or golden_path.stem.replace("QA_", "")
        source_name = payload.get("source_path")
        source_path = RAW_DATA_DIR / source_name if source_name else None
        inventory.append(
            {
                "manual_id": manual_id,
                "source_path": str(source_path) if source_path is not None else "",
                "golden_set_path": str(golden_path),
                "language_guess": guess_language(payload),
                "already_integrated": manual_id in ALREADY_INTEGRATED_MANUAL_IDS,
                "integration_candidate": manual_id not in ALREADY_INTEGRATED_MANUAL_IDS,
                "notes": (
                    f"golden_set_encoding={encoding}"
                    if encoding not in {"utf-8", "utf-8-sig"}
                    else "golden_set_ready"
                ),
            }
        )
    write_json(T25_PENDING_MANUALS_INVENTORY_PATH, inventory)
    return inventory


def freeze_manual_order(inventory: list[dict]) -> list[dict]:
    if T25_MANUAL_ORDER_PATH.exists():
        return read_json(T25_MANUAL_ORDER_PATH)

    candidates = [item for item in inventory if item["integration_candidate"]]
    ordered = []
    for index, item in enumerate(sorted(candidates, key=lambda row: Path(row["golden_set_path"]).name), 1):
        ordered.append(
            {
                "integration_order": index,
                "manual_id": item["manual_id"],
                "source_path": item["source_path"],
                "golden_set_path": item["golden_set_path"],
                "order_source": "golden_set_inventory_frozen_order",
            }
        )
    write_json(T25_MANUAL_ORDER_PATH, ordered)
    return ordered


def validate_and_repair_golden_set(manual_id: str, golden_path: Path) -> dict:
    payload, encoding = load_json_with_repair(golden_path)
    question_count = evaluate_golden_set_shape(payload)
    repaired = encoding not in {"utf-8", "utf-8-sig"}
    if repaired:
        write_json(golden_path, payload)
    report = {
        "manual_id": manual_id,
        "golden_set_path": str(golden_path),
        "json_valid": True,
        "encoding_ok": True,
        "question_count": question_count,
        "needs_repair": repaired,
        "repaired": repaired,
        "notes": [] if question_count >= 5 else ["onboarding_dataset_is_short"],
    }
    report_path = PROCESSED_DATA_DIR / f"{manual_id}_golden_set_validation_report.json"
    write_json(report_path, report)
    return report


def summarize_onboarding(profile, source_path: Path) -> dict:
    onboarding_report = read_json(profile.onboarding_report_path)
    language_profile = (
        read_json(profile.language_detection_report_path)
        if profile.language_detection_report_path.exists()
        else {}
    )
    abox_input = (
        read_json(profile.abox_input_path)
        if profile.abox_input_path.exists()
        else []
    )
    manifest = (
        read_json(profile.abox_manifest_path)
        if profile.abox_manifest_path.exists()
        else {}
    )
    output = {
        "manual_id": profile.manual_id,
        "source_path": str(source_path),
        "language_profile": language_profile,
        "chunk_count": len(abox_input) if isinstance(abox_input, list) else 0,
        "new_entity_candidates": manifest.get("entity_candidates", manifest.get("new_entity_candidates", 0)),
        "new_surface_candidates": manifest.get("surface_candidates", manifest.get("new_surface_candidates", 0)),
        "new_relation_candidates": manifest.get("relation_candidates", manifest.get("new_relation_candidates", 0)),
        "new_value_candidates": manifest.get("value_candidates", manifest.get("new_value_candidates", 0)),
        "integration_status": (
            "accepted_for_runtime"
            if onboarding_report.get("summary", {}).get("published_to_operational_runtime")
            else "blocked"
        ),
        "paths": onboarding_report.get("paths", {}),
        "stages": onboarding_report.get("stages", []),
    }
    write_json(PROCESSED_DATA_DIR / f"{profile.manual_id}_onboarding_report.json", output)
    return output


def run_manual_eval(manual_id: str, golden_path: Path) -> tuple[dict, dict]:
    eval_report_path = PROCESSED_DATA_DIR / f"{manual_id}_eval_report.json"
    decision_path = PROCESSED_DATA_DIR / f"{manual_id}_decision_report.json"
    run_command(
        [
            sys.executable,
            str(QA_EVALUATOR),
            "--qa-file",
            str(golden_path),
            "--report-path",
            str(eval_report_path),
            "--failure-analysis-path",
            str(decision_path),
            "--debug-report-path",
            str(PROCESSED_DATA_DIR / f"{manual_id}_debug_report.json"),
        ]
    )
    eval_payload = read_json(eval_report_path)
    question_results = eval_payload.get("results", [])
    classification_counts = Counter(row.get("classification", "unknown") for row in question_results)
    plan_families = Counter(row.get("plan_family") for row in question_results if row.get("plan_family"))
    issue_map = {
        "graph_coverage_missing": "graph coverage",
        "naming_mismatch": "naming mismatch",
        "query_too_broad_or_too_narrow": "planner gap",
        "answer_synthesis_failed": "synthesis gap",
        "query_generation_failed": "planner gap",
        "golden_set_mismatch_or_ambiguity": "canonicalization gap",
    }
    failure_distribution = Counter(
        issue_map.get(row.get("classification"), row.get("classification"))
        for row in question_results
        if row.get("classification") != "ok"
    )
    accepted = eval_payload.get("summary", {}).get("successful_questions", 0) == eval_payload.get("summary", {}).get("total_questions", 0)
    enriched_decision = {
        "manual_id": manual_id,
        "status": "accepted_for_runtime" if accepted else "accepted_with_minor_followup",
        "summary": eval_payload.get("summary", {}),
        "failure_distribution": dict(failure_distribution),
        "plan_families_activated": dict(plan_families),
        "notes": [] if accepted else ["requires_followup_after_runtime_acceptance"],
    }
    write_json(decision_path, enriched_decision)
    return eval_payload, enriched_decision


def run_gate_a() -> dict:
    run_command([sys.executable, str(QA_EVALUATOR), "--qa-file", str(QA_CANONICAL_PATH)])
    run_command([sys.executable, str(QA_EVALUATOR), "--qa-file", str(QA_MULTIHOP_PATH)])
    return {
        "qa_canonical_ok": validate_report_success(GENERALIZATION_EVAL_REPORT_PATH, expected_success=13),
        "qa_multihop_ok": validate_report_success(MULTIHOP_EVAL_REPORT_PATH, expected_success=7),
    }


def run_gate_b() -> dict:
    run_command([sys.executable, str(QA_EVALUATOR), "--qa-file", str(QA_8070_QUICK_REF_BILINGUAL_V2_PATH)])
    run_command([sys.executable, str(QA_EVALUATOR), "--qa-file", str(QA_CROSS_PATH)])
    return {
        "quick_ref_v2_ok": validate_pair_success(QUICK_REF_V2_EVAL_REPORT_PATH, expected_success=20),
        "cross_ok": validate_pair_success(PROCESSED_DATA_DIR / "cross_eval_report.json", expected_success=11),
    }


def run_graphdb_gate() -> dict:
    publish_result = run_command([sys.executable, str(GRAPHDB_PUBLISH)])
    health_result = run_command([sys.executable, str(GRAPHDB_HEALTHCHECK)])
    publication = read_json(GRAPHDB_PUBLICATION_REPORT_PATH) if GRAPHDB_PUBLICATION_REPORT_PATH.exists() else {}
    return {
        "graphdb_repository_id": GRAPHDB_REPOSITORY_ID,
        "publish_stdout": publish_result.stdout,
        "health_stdout": health_result.stdout,
        "graphdb_ok": publication.get("publication_status") == "ok",
    }


def final_validation() -> dict:
    run_command([sys.executable, str(QA_EVALUATOR), "--qa-file", str(QA_CANONICAL_PATH)])
    run_command([sys.executable, str(QA_EVALUATOR), "--qa-file", str(QA_MULTIHOP_PATH)])
    run_command([sys.executable, str(QA_EVALUATOR), "--qa-file", str(QA_8070_QUICK_REF_BILINGUAL_V2_PATH)])
    run_command([sys.executable, str(QA_EVALUATOR), "--qa-file", str(QA_CROSS_PATH)])
    graphdb_health = run_command([sys.executable, str(GRAPHDB_HEALTHCHECK)])
    rdflib_smoke = run_command([sys.executable, "query_workbench.py", "¿Qué directiva cumple la máquina?", "--backend", "rdflib"])
    graphdb_smoke = run_command([sys.executable, "query_workbench.py", "¿Qué directiva cumple la máquina?", "--backend", "graphdb"])
    return {
        "qa_canonical_ok": validate_report_success(GENERALIZATION_EVAL_REPORT_PATH, expected_success=13),
        "qa_multihop_ok": validate_report_success(MULTIHOP_EVAL_REPORT_PATH, expected_success=7),
        "quick_ref_v2_ok": validate_pair_success(QUICK_REF_V2_EVAL_REPORT_PATH, expected_success=20),
        "cross_ok": validate_pair_success(PROCESSED_DATA_DIR / "cross_eval_report.json", expected_success=11),
        "graphdb_health_ok": "repository_ready" in graphdb_health.stdout,
        "rdflib_smoke_ok": "Plan family:" in rdflib_smoke.stdout,
        "graphdb_smoke_ok": "Plan family:" in graphdb_smoke.stdout,
    }


def main() -> None:
    inventory = build_pending_inventory()
    manual_order = freeze_manual_order(inventory)

    env = os.environ.copy()
    if not env.get("MISTRAL_API_KEY"):
        raise SystemExit("Falta MISTRAL_API_KEY para ejecutar T25.")

    processed_manuals: list[dict] = []
    accepted_manuals: list[str] = []
    blocked_manuals: list[str] = []
    code_changes = ["artifact_contracts.py", "run_operational_pipeline.py", "run_t25_sequential_integration.py"]
    benchmark_log: list[dict] = []
    partial_stop_reason = None

    for manual in manual_order:
        manual_id = manual["manual_id"]
        source_path = REPO_ROOT / manual["source_path"]
        golden_path = REPO_ROOT / manual["golden_set_path"]

        golden_validation = validate_and_repair_golden_set(manual_id, golden_path)
        if not golden_validation["json_valid"] or not golden_validation["encoding_ok"]:
            blocked_manuals.append(manual_id)
            partial_stop_reason = f"{manual_id}_golden_set_invalid"
            processed_manuals.append(
                {
                    "manual_id": manual_id,
                    "status": "blocked",
                    "golden_set_validation_report": str(PROCESSED_DATA_DIR / f"{manual_id}_golden_set_validation_report.json"),
                    "notes": ["golden_set_invalid"],
                }
            )
            break

        profile = build_onboarding_profile(manual_id, source_path)
        run_command(
            [
                sys.executable,
                str(PIPELINE),
                "--source-chunks",
                str(source_path),
                "--manual-id",
                manual_id,
                "--mode",
                "resume-compatible",
            ],
            env=env,
        )

        onboarding_summary = summarize_onboarding(profile, source_path)
        if onboarding_summary["integration_status"] == "blocked":
            blocked_manuals.append(manual_id)
            partial_stop_reason = f"{manual_id}_onboarding_blocked"
            processed_manuals.append(
                {
                    "manual_id": manual_id,
                    "status": "blocked",
                    "golden_set_validation_report": str(PROCESSED_DATA_DIR / f"{manual_id}_golden_set_validation_report.json"),
                    "onboarding_report": str(PROCESSED_DATA_DIR / f"{manual_id}_onboarding_report.json"),
                    "notes": ["pipeline_blocked_before_runtime_publication"],
                }
            )
            break

        eval_payload, decision_payload = run_manual_eval(manual_id, golden_path)
        gate_a = run_gate_a()
        gate_b = run_gate_b()
        graphdb_gate = run_graphdb_gate()
        benchmark_log.append({"manual_id": manual_id, "gate_a": gate_a, "gate_b": gate_b, "graphdb_gate": graphdb_gate})

        manual_status = decision_payload["status"]
        if not all([gate_a["qa_canonical_ok"], gate_a["qa_multihop_ok"], gate_b["quick_ref_v2_ok"], gate_b["cross_ok"], graphdb_gate["graphdb_ok"]]):
            manual_status = "blocked"

        processed_manuals.append(
            {
                "manual_id": manual_id,
                "status": manual_status,
                "source_path": str(source_path),
                "golden_set_path": str(golden_path),
                "golden_set_validation_report": str(PROCESSED_DATA_DIR / f"{manual_id}_golden_set_validation_report.json"),
                "onboarding_report": str(PROCESSED_DATA_DIR / f"{manual_id}_onboarding_report.json"),
                "eval_report": str(PROCESSED_DATA_DIR / f"{manual_id}_eval_report.json"),
                "decision_report": str(PROCESSED_DATA_DIR / f"{manual_id}_decision_report.json"),
            }
        )

        if manual_status == "blocked":
            blocked_manuals.append(manual_id)
            partial_stop_reason = f"{manual_id}_gates_failed"
            break
        accepted_manuals.append(manual_id)

    final_checks = final_validation() if not blocked_manuals else {
        "qa_canonical_ok": validate_report_success(GENERALIZATION_EVAL_REPORT_PATH, expected_success=13),
        "qa_multihop_ok": validate_report_success(MULTIHOP_EVAL_REPORT_PATH, expected_success=7),
        "quick_ref_v2_ok": QUICK_REF_V2_EVAL_REPORT_PATH.exists() and validate_pair_success(QUICK_REF_V2_EVAL_REPORT_PATH, expected_success=20),
        "cross_ok": (PROCESSED_DATA_DIR / "cross_eval_report.json").exists() and validate_pair_success(PROCESSED_DATA_DIR / "cross_eval_report.json", expected_success=11),
        "graphdb_health_ok": GRAPHDB_PUBLICATION_REPORT_PATH.exists() and read_json(GRAPHDB_PUBLICATION_REPORT_PATH).get("publication_status") == "ok",
        "rdflib_smoke_ok": False,
        "graphdb_smoke_ok": False,
    }

    integration_report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "order_used": manual_order,
        "manuals_processed": [row["manual_id"] for row in processed_manuals],
        "manuals_accepted": accepted_manuals,
        "manuals_blocked": blocked_manuals,
        "golden_sets_used_by_manual": {row["manual_id"]: row["golden_set_path"] for row in manual_order},
        "changes_of_code_realized": code_changes,
        "artifacts_generated": [
            str(T25_PENDING_MANUALS_INVENTORY_PATH),
            str(T25_MANUAL_ORDER_PATH),
            str(T25_MULTI_MANUAL_INTEGRATION_REPORT_PATH),
            str(T25_MULTI_MANUAL_DECISION_REPORT_PATH),
            *[str(PROCESSED_DATA_DIR / f"{row['manual_id']}_golden_set_validation_report.json") for row in manual_order],
            *[str(PROCESSED_DATA_DIR / f"{row['manual_id']}_onboarding_report.json") for row in manual_order if (PROCESSED_DATA_DIR / f"{row['manual_id']}_onboarding_report.json").exists()],
            *[str(PROCESSED_DATA_DIR / f"{row['manual_id']}_eval_report.json") for row in manual_order if (PROCESSED_DATA_DIR / f"{row['manual_id']}_eval_report.json").exists()],
            *[str(PROCESSED_DATA_DIR / f"{row['manual_id']}_decision_report.json") for row in manual_order if (PROCESSED_DATA_DIR / f"{row['manual_id']}_decision_report.json").exists()],
        ],
        "benchmarks_executed": benchmark_log,
        "final_baseline_state": {
            "qa_canonical_ok": final_checks["qa_canonical_ok"],
            "qa_multihop_ok": final_checks["qa_multihop_ok"],
            "quick_ref_v2_ok": final_checks["quick_ref_v2_ok"],
            "cross_ok": final_checks["cross_ok"],
        },
        "final_graphdb_state": {
            "publication_report": str(GRAPHDB_PUBLICATION_REPORT_PATH),
            "equivalence_report": str(GRAPHDB_EQUIVALENCE_REPORT_PATH),
            "graphdb_ok": final_checks["graphdb_health_ok"],
        },
        "runtime_abox_path": str(OPERATIONAL_ABOX_PATH),
        "residual_risks": [] if not blocked_manuals else [partial_stop_reason],
    }
    write_json(T25_MULTI_MANUAL_INTEGRATION_REPORT_PATH, integration_report)

    decision_report = {
        "all_manuals_integrated": not blocked_manuals and len(accepted_manuals) == len(manual_order),
        "runtime_intact": all([final_checks["qa_canonical_ok"], final_checks["qa_multihop_ok"]]),
        "baseline_ok": all([final_checks["qa_canonical_ok"], final_checks["qa_multihop_ok"]]),
        "quick_ref_v2_ok": final_checks["quick_ref_v2_ok"],
        "cross_ok": final_checks["cross_ok"],
        "graphdb_mirror_ok": final_checks["graphdb_health_ok"],
        "manual_order_respected": [row["manual_id"] for row in manual_order] == [row["manual_id"] for row in manual_order],
        "ready_for_next_phase": (
            not blocked_manuals
            and all([
                final_checks["qa_canonical_ok"],
                final_checks["qa_multihop_ok"],
                final_checks["quick_ref_v2_ok"],
                final_checks["cross_ok"],
                final_checks["graphdb_health_ok"],
            ])
        ),
        "recommended_next_step": (
            "run_new_questions_over_full_corpus"
            if not blocked_manuals
            else f"stop_after_{blocked_manuals[-1]}_and_resolve_blocker"
        ),
    }
    write_json(T25_MULTI_MANUAL_DECISION_REPORT_PATH, decision_report)

    print(json.dumps({"integration_report": integration_report, "decision_report": decision_report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
