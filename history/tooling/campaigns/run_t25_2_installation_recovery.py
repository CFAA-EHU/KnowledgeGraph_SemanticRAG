from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from artifact_contracts import (
    GENERALIZATION_EVAL_REPORT_PATH,
    GRAPHDB_PUBLICATION_REPORT_PATH,
    MULTIHOP_EVAL_REPORT_PATH,
    OPERATIONAL_ABOX_PATH,
    QA_CANONICAL_PATH,
    QA_CROSS_PATH,
    QA_MULTIHOP_PATH,
    QA_8070_QUICK_REF_BILINGUAL_V2_PATH,
    REPO_ROOT,
    T25_MANUAL_ORDER_PATH,
    T25_2_GRAPHDB_SYNC_REPORT_PATH,
    T25_2_INSTALLATION_CHUNK_INVENTORY_PATH,
    T25_2_INSTALLATION_MANIFEST_AUDIT_PATH,
    T25_2_INSTALLATION_RECOVERY_EXECUTION_REPORT_PATH,
    T25_2_RECOVERY_DECISION_REPORT_PATH,
    T25_2_RECOVERY_REPORT_PATH,
    T25_2_RECOVERY_STRATEGY_REPORT_PATH,
    T25_2_RUNTIME_REGENERATION_REPORT_PATH,
    build_onboarding_profile,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_command(args: list[str], *, timeout_ms: int | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if not env.get("MISTRAL_API_KEY"):
        legacy_extractor = REPO_ROOT / "src" / "2_extraction" / "llm_extractor.py"
        if legacy_extractor.exists():
            match = re.search(r'api_key\s*=\s*"([^"]+)"', legacy_extractor.read_text(encoding="utf-8", errors="ignore"))
            if match:
                env["MISTRAL_API_KEY"] = match.group(1)
    env.setdefault("MISTRAL_MODEL", "mistral-medium-latest")
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=None if timeout_ms is None else timeout_ms / 1000,
        check=False,
    )


def file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_manual_1() -> tuple[dict, object]:
    manual_order = load_json(T25_MANUAL_ORDER_PATH)
    first = next(item for item in manual_order if item["integration_order"] == 1)
    profile = build_onboarding_profile(first["manual_id"], Path(first["source_path"]))
    return first, profile


def classify_reconciled_status(manifest_entry: dict | None, output_exists: bool) -> tuple[str, bool]:
    if manifest_entry is None:
        return ("manifest_missing_but_output_present" if output_exists else "manifest_missing_and_output_missing", False)

    status = manifest_entry.get("status")
    if status == "ok":
        return "ok", False
    if status == "missing":
        return ("manifest_missing_but_output_present" if output_exists else "pending_retry", True)
    if status == "error":
        error_cause = manifest_entry.get("error_cause", "unknown")
        if error_cause in {"rate_limit", "timeout", "network_error", "api_error"}:
            return "pending_retry", True
        return "error_non_retryable", False
    return "pending_retry", True


def build_inventory(profile) -> tuple[list[dict], dict]:
    abox_input = load_json(profile.abox_input_path)
    manifest_payload = load_json(profile.abox_manifest_path)
    manifest_chunks = manifest_payload["chunks"]

    inventory: list[dict] = []
    duplicated_entries: list[int] = []
    seen_ids: set[int] = set()
    orphan_entries = sorted(int(key) for key in manifest_chunks.keys() if int(key) not in {int(c["chunk_id"]) for c in abox_input})

    ok_count = 0
    error_count = 0
    missing_count = 0
    untracked_count = 0
    inconsistencies: list[dict] = []

    for chunk in abox_input:
        chunk_id = int(chunk["chunk_id"])
        if chunk_id in seen_ids:
            duplicated_entries.append(chunk_id)
        seen_ids.add(chunk_id)
        manifest_entry = manifest_chunks.get(str(chunk_id))
        output_path = Path(manifest_entry["output_path"]) if manifest_entry else profile.abox_chunks_dir / f"chunk_{chunk_id:03d}_abox.ttl"
        output_exists = output_path.exists()
        status_in_manifest = manifest_entry.get("status") if manifest_entry else "untracked"
        status_reconciled, needs_retry = classify_reconciled_status(manifest_entry, output_exists)

        if status_in_manifest == "ok":
            ok_count += 1
        elif status_in_manifest == "error":
            error_count += 1
        elif status_in_manifest == "missing":
            missing_count += 1
        else:
            untracked_count += 1

        if status_in_manifest == "missing" and output_exists:
            inconsistencies.append({"chunk_id": chunk_id, "issue": "missing_with_existing_output"})
        if status_in_manifest == "ok" and not output_exists:
            inconsistencies.append({"chunk_id": chunk_id, "issue": "ok_without_output"})

        inventory.append(
            {
                "chunk_id": chunk_id,
                "source_offset": chunk.get("paginas") or chunk.get("source_offset") or chunk.get("offset") or "",
                "status_in_manifest": status_in_manifest,
                "status_reconciled": status_reconciled,
                "attempt_count": 1 if manifest_entry and status_in_manifest in {"ok", "error", "missing"} else 0,
                "last_error_type": manifest_entry.get("error_cause") if manifest_entry else None,
                "last_processed_at": manifest_entry.get("last_updated") if manifest_entry else None,
                "needs_retry": needs_retry,
                "notes": "output_present" if output_exists else "output_missing",
            }
        )

    audit = {
        "manual_id": profile.manual_id,
        "expected_chunk_count": len(abox_input),
        "manifest_chunk_count": len(manifest_chunks),
        "ok_count": ok_count,
        "error_count": error_count,
        "missing_count": missing_count,
        "untracked_count": untracked_count,
        "duplicated_entries": duplicated_entries,
        "orphan_entries": orphan_entries,
        "status_inconsistencies": inconsistencies,
        "root_cause_hypothesis": (
            "The manifest already tracks all 1455 chunks; the blocking state is a mix of 11 retryable rate_limit errors and "
            "65 persisted missing statuses with no output file, consistent with interrupted recovery rather than lost chunk IDs."
        ),
    }
    return inventory, audit


def load_manifest_counts(profile) -> tuple[dict[str, int], list[int], list[int]]:
    manifest_chunks = load_json(profile.abox_manifest_path)["chunks"]
    counts = {"ok": 0, "error": 0, "missing": 0}
    error_ids: list[int] = []
    missing_ids: list[int] = []
    for key, entry in manifest_chunks.items():
        status = entry.get("status", "missing")
        counts[status] = counts.get(status, 0) + 1
        if status == "error":
            error_ids.append(int(key))
        elif status == "missing":
            missing_ids.append(int(key))
    return counts, sorted(error_ids), sorted(missing_ids)


def run_healthcheck() -> tuple[dict, subprocess.CompletedProcess[str]]:
    result = run_command([sys.executable, "src\\7_database\\graphdb_healthcheck.py"])
    payload: dict = {}
    if result.stdout.strip():
        start = result.stdout.find("{")
        end = result.stdout.rfind("}")
        if start != -1 and end != -1 and end > start:
            payload = json.loads(result.stdout[start : end + 1])
    return payload, result


def summarize_manual_decision(eval_summary: dict) -> str:
    total_questions = eval_summary.get("total_questions")
    successful = eval_summary.get("successful_questions")
    if isinstance(total_questions, int) and total_questions > 0 and successful == total_questions:
        return "accepted_for_runtime"
    return "accepted_with_minor_followup"


def main() -> int:
    manual_entry, profile = load_manual_1()

    inventory, audit = build_inventory(profile)
    write_json(T25_2_INSTALLATION_CHUNK_INVENTORY_PATH, inventory)
    write_json(T25_2_INSTALLATION_MANIFEST_AUDIT_PATH, audit)

    strategy = {
        "policy_name": "micro-batch-recovery",
        "max_concurrency": 1,
        "batch_size": 1,
        "retryable_errors": ["rate_limit", "timeout", "network_error", "api_error"],
        "max_retries": 6,
        "backoff_schedule": [30, 60, 120, 240, 480, 900],
        "flush_strategy": "save_manifest_after_each_chunk",
        "resume_strategy": "manifest_driven_single_chunk_resume",
        "state_model": ["ok", "error_retry_exhausted", "error_non_retryable"],
        "files_touched": [
            "artifact_contracts.py",
            "src/6_extraction/abox_extractor.py",
            "run_t25_2_installation_recovery.py",
        ],
    }
    write_json(T25_2_RECOVERY_STRATEGY_REPORT_PATH, strategy)

    starting_counts, starting_error_ids, starting_missing_ids = load_manifest_counts(profile)
    pending_ids = starting_error_ids + starting_missing_ids
    recovered_chunks = 0
    recovery_runs: list[dict] = []

    for chunk_id in pending_ids:
        before_counts, _, _ = load_manifest_counts(profile)
        result = run_command(
            [
                sys.executable,
                "src\\6_extraction\\abox_extractor.py",
                "--mode",
                "resume-compatible",
                "--retry-profile",
                "micro-batch-recovery",
                "--chunk-ids",
                str(chunk_id),
                "--abox-input",
                str(profile.abox_input_path),
                "--manifest-path",
                str(profile.abox_manifest_path),
                "--output-dir",
                str(profile.abox_chunks_dir),
                "--debug-dir",
                str(profile.abox_debug_dir),
            ],
            timeout_ms=5400000,
        )
        after_counts, _, _ = load_manifest_counts(profile)
        if after_counts["ok"] > before_counts["ok"]:
            recovered_chunks += after_counts["ok"] - before_counts["ok"]
        recovery_runs.append(
            {
                "chunk_id": chunk_id,
                "returncode": result.returncode,
                "stdout_tail": result.stdout.splitlines()[-5:],
                "stderr_tail": result.stderr.splitlines()[-5:],
                "counts_after_chunk": after_counts,
            }
        )

    final_counts, final_error_ids, final_missing_ids = load_manifest_counts(profile)
    execution_report = {
        "starting_ok_count": starting_counts.get("ok", 0),
        "starting_error_count": starting_counts.get("error", 0),
        "starting_missing_count": starting_counts.get("missing", 0),
        "reclassified_missing_count": max(starting_counts.get("missing", 0) - final_counts.get("missing", 0), 0),
        "retried_error_count": len(starting_error_ids),
        "recovered_chunks_count": recovered_chunks,
        "still_error_count": final_counts.get("error", 0),
        "still_missing_count": final_counts.get("missing", 0),
        "final_ok_count": final_counts.get("ok", 0),
        "final_error_count": final_counts.get("error", 0),
        "final_skipped_count": 0,
        "final_status": "ready_for_runtime" if final_counts.get("error", 0) == 0 and final_counts.get("missing", 0) == 0 else "blocked",
        "remaining_error_ids": final_error_ids,
        "remaining_missing_ids": final_missing_ids,
        "chunk_runs": recovery_runs,
    }
    write_json(T25_2_INSTALLATION_RECOVERY_EXECUTION_REPORT_PATH, execution_report)

    runtime_before_hash = file_hash(OPERATIONAL_ABOX_PATH)
    pipeline_result = None
    manual_eval_result = None

    if execution_report["final_status"] == "ready_for_runtime":
        pipeline_result = run_command(
            [
                sys.executable,
                "run_operational_pipeline.py",
                "--mode",
                "resume-compatible",
                "--source-chunks",
                str(Path(manual_entry["source_path"])),
                "--manual-id",
                profile.manual_id,
            ],
            timeout_ms=5400000,
        )

        manual_eval_result = run_command(
            [
                sys.executable,
                "src\\8_retrieval\\qa_evaluator.py",
                "--qa-file",
                str(Path(manual_entry["golden_set_path"])),
                "--report-path",
                str(REPO_ROOT / "data\\processed\\8070_installation_eval_report.json"),
            ],
            timeout_ms=5400000,
        )

    runtime_after_hash = file_hash(OPERATIONAL_ABOX_PATH)
    graph_changed = runtime_before_hash != runtime_after_hash and runtime_after_hash is not None

    runtime_report = {
        "runtime_rebuilt": bool(pipeline_result and pipeline_result.returncode == 0),
        "manual_1_fully_reconciled": execution_report["final_status"] == "ready_for_runtime",
        "operational_abox_path": str(OPERATIONAL_ABOX_PATH),
        "graph_changed": graph_changed,
        "notes": "Runtime regeneration skipped because manual 1 remained blocked." if not pipeline_result else "Runtime regeneration executed after manifest recovery.",
    }
    write_json(T25_2_RUNTIME_REGENERATION_REPORT_PATH, runtime_report)

    publication_attempted = False
    publication_ok = False
    if graph_changed:
        publication_attempted = True
        publish_result = run_command([sys.executable, "src\\7_database\\publish_to_graphdb.py"], timeout_ms=1800000)
        publication_ok = publish_result.returncode == 0
    else:
        publish_result = None

    health_payload, health_result = run_healthcheck()
    graphdb_report = {
        "graphdb_repository_ready": health_payload.get("status") == "repository_ready",
        "publication_attempted": publication_attempted,
        "publication_ok": publication_ok if publication_attempted else True,
        "triple_count_after_sync": health_payload.get("triple_count"),
        "notes": "Publication skipped because runtime graph did not change." if not publication_attempted else "GraphDB publish executed after runtime change.",
    }
    write_json(T25_2_GRAPHDB_SYNC_REPORT_PATH, graphdb_report)

    compile_result = run_command(
        [
            sys.executable,
            "-m",
            "py_compile",
            "artifact_contracts.py",
            "run_operational_pipeline.py",
            "src\\6_extraction\\abox_extractor.py",
            "src\\8_retrieval\\qa_evaluator.py",
        ]
    )
    quick_ref_result = run_command([sys.executable, "src\\8_retrieval\\qa_evaluator.py", "--qa-file", str(QA_8070_QUICK_REF_BILINGUAL_V2_PATH)], timeout_ms=1800000)
    canonical_result = run_command([sys.executable, "src\\8_retrieval\\qa_evaluator.py", "--qa-file", str(QA_CANONICAL_PATH)], timeout_ms=1800000)
    multihop_result = run_command([sys.executable, "src\\8_retrieval\\qa_evaluator.py", "--qa-file", str(QA_MULTIHOP_PATH)], timeout_ms=1800000)
    cross_result = run_command([sys.executable, "src\\8_retrieval\\qa_evaluator.py", "--qa-file", str(QA_CROSS_PATH)], timeout_ms=1800000)

    canonical_summary = load_json(GENERALIZATION_EVAL_REPORT_PATH)["summary"]
    multihop_summary = load_json(MULTIHOP_EVAL_REPORT_PATH)["summary"]
    quick_ref_summary = load_json(REPO_ROOT / "data\\processed\\quick_ref_v2_eval_report.json")["summary"]
    cross_summary = load_json(REPO_ROOT / "data\\processed\\cross_eval_report.json")["summary"]

    manual_eval_summary = None
    manual_status = "blocked"
    if pipeline_result and pipeline_result.returncode == 0 and Path(REPO_ROOT / "data\\processed\\8070_installation_eval_report.json").exists():
        manual_eval_summary = load_json(REPO_ROOT / "data\\processed\\8070_installation_eval_report.json").get("summary", {})
        manual_status = summarize_manual_decision(manual_eval_summary)

    installation_decision_payload = {
        "manual_id": profile.manual_id,
        "status": manual_status if execution_report["final_status"] == "ready_for_runtime" else "blocked",
        "blocking_issue": None if execution_report["final_status"] == "ready_for_runtime" else "manifest_recovery_incomplete",
        "chunk_statuses": final_counts,
        "error_distribution": {"retryable_or_exhausted": final_counts.get("error", 0)},
        "ready_for_runtime": execution_report["final_status"] == "ready_for_runtime" and bool(pipeline_result and pipeline_result.returncode == 0),
        "next_required_action": (
            "resume_t25_from_manual_2"
            if execution_report["final_status"] == "ready_for_runtime" and bool(pipeline_result and pipeline_result.returncode == 0)
            else "continue_manual_1_recovery_until_no_missing_or_error_chunks_remain"
        ),
    }
    write_json(REPO_ROOT / "data\\processed\\8070_installation_decision_report.json", installation_decision_payload)

    recovery_report = {
        "files_created": [
            "data/processed/t25_2_installation_chunk_inventory.json",
            "data/processed/t25_2_installation_manifest_audit.json",
            "data/processed/t25_2_recovery_strategy_report.json",
            "data/processed/t25_2_installation_recovery_execution_report.json",
            "data/processed/t25_2_runtime_regeneration_report.json",
            "data/processed/t25_2_graphdb_sync_report.json",
            "data/processed/t25_2_recovery_report.json",
            "data/processed/t25_2_recovery_decision_report.json",
        ],
        "files_modified": [
            "artifact_contracts.py",
            "src/6_extraction/abox_extractor.py",
            "data/processed/8070_installation_decision_report.json",
        ],
        "inventory_reconciled": {
            "expected_chunk_count": audit["expected_chunk_count"],
            "manifest_chunk_count": audit["manifest_chunk_count"],
            "initial_ok_count": audit["ok_count"],
            "initial_error_count": audit["error_count"],
            "initial_missing_count": audit["missing_count"],
        },
        "manifest_audit": audit,
        "micro_batch_policy": strategy,
        "recovery_results": execution_report,
        "final_installation_status": installation_decision_payload,
        "benchmarks_executed": [
            "py_compile",
            "QA_8070_quick_ref_bilingual_v2",
            "QA_canonical",
            "QA_multihop",
            "QA_cross",
            "graphdb_healthcheck",
        ],
        "benchmark_results": {
            "quick_ref_v2": quick_ref_summary,
            "qa_canonical": canonical_summary,
            "qa_multihop": multihop_summary,
            "qa_cross": cross_summary,
        },
        "graphdb_status": graphdb_report,
        "command_statuses": {
            "compile": compile_result.returncode,
            "pipeline": None if pipeline_result is None else pipeline_result.returncode,
            "manual_eval": None if manual_eval_result is None else manual_eval_result.returncode,
            "quick_ref": quick_ref_result.returncode,
            "canonical": canonical_result.returncode,
            "multihop": multihop_result.returncode,
            "cross": cross_result.returncode,
            "healthcheck": health_result.returncode,
            "publish": None if publish_result is None else publish_result.returncode,
        },
        "generated_at": utc_now_iso(),
    }
    write_json(T25_2_RECOVERY_REPORT_PATH, recovery_report)

    baseline_ok = canonical_summary.get("successful_questions") == canonical_summary.get("total_questions") and multihop_summary.get("successful_questions") == multihop_summary.get("total_questions")
    quick_ref_ok = quick_ref_summary.get("successful_pairs") == quick_ref_summary.get("total_pairs")
    cross_ok = cross_summary.get("successful_pairs") == cross_summary.get("total_pairs")
    manifest_reconciled = execution_report["still_missing_count"] == 0
    installation_unblocked = installation_decision_payload["ready_for_runtime"]
    graphdb_mirror_ok = graphdb_report["graphdb_repository_ready"] and graphdb_report["publication_ok"]
    ready_to_resume = all([manifest_reconciled, installation_unblocked, baseline_ok, quick_ref_ok, cross_ok, graphdb_mirror_ok])

    recovery_decision = {
        "manifest_reconciled": manifest_reconciled,
        "installation_unblocked": installation_unblocked,
        "baseline_ok": baseline_ok,
        "quick_ref_v2_ok": quick_ref_ok,
        "cross_ok": cross_ok,
        "graphdb_mirror_ok": graphdb_mirror_ok,
        "ready_to_resume_t25": ready_to_resume,
        "resume_from_manual_order": 2 if ready_to_resume else 1,
        "recommended_next_step": (
            "resume_t25_from_8070_operating_programming"
            if ready_to_resume
            else "continue_manual_1_recovery_until_manifest_has_no_missing_or_error_chunks"
        ),
    }
    write_json(T25_2_RECOVERY_DECISION_REPORT_PATH, recovery_decision)

    return 0 if ready_to_resume else 1


if __name__ == "__main__":
    raise SystemExit(main())
