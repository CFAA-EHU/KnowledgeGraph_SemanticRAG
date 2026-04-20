from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

CORE_POLICY_PATH = PROCESSED_DIR / "t27_core_vs_project_policy.json"
ENTRYPOINT_CONTRACT_PATH = PROCESSED_DIR / "t27_stable_entrypoint_contract.json"
HISTORICAL_REGISTRY_PATH = PROCESSED_DIR / "t27_historical_tooling_registry.json"
PROCESSED_POLICY_PATH = PROCESSED_DIR / "t27_processed_artifact_policy.json"
DOCUMENTATION_REPORT_PATH = PROCESSED_DIR / "t27_documentation_alignment_report.json"

CANONICAL_REPORT_PATH = PROCESSED_DIR / "generalization_eval_report.json"
MULTIHOP_REPORT_PATH = PROCESSED_DIR / "multihop_eval_report.json"
QUICK_REF_REPORT_PATH = PROCESSED_DIR / "quick_ref_v2_eval_report.json"
CROSS_REPORT_PATH = PROCESSED_DIR / "cross_eval_report.json"

CLEANUP_REPORT_PATH = PROCESSED_DIR / "t27_repo_cleanup_report.json"
DECISION_REPORT_PATH = PROCESSED_DIR / "t27_repo_cleanup_decision_report.json"

PY_COMPILE_TARGETS = [
    "artifact_contracts.py",
    "run_operational_pipeline.py",
    "run_runtime_clean_rebuild.py",
    "src/6_extraction/abox_extractor.py",
    "src/8_retrieval/text_to_sparql.py",
    "src/8_retrieval/multilingual_query_normalizer.py",
    "src/8_retrieval/synthesis_pipeline.py",
    "src/8_retrieval/qa_evaluator.py",
    "src/7_database/publish_to_graphdb.py",
    "src/7_database/graphdb_healthcheck.py",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def relpath(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def run_py_compile() -> dict[str, Any]:
    command = [sys.executable, "-m", "py_compile", *PY_COMPILE_TARGETS]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": " ".join(command),
        "targets": PY_COMPILE_TARGETS,
        "passed": completed.returncode == 0,
        "return_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def run_graphdb_healthcheck() -> dict[str, Any]:
    command = [sys.executable, "src/7_database/graphdb_healthcheck.py"]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    parsed_stdout: dict[str, Any] | None = None
    stdout = completed.stdout.strip()
    if stdout:
        parsed_stdout = json.loads(stdout)
    return {
        "command": " ".join(command),
        "passed": completed.returncode == 0,
        "return_code": completed.returncode,
        "stdout": parsed_stdout,
        "stderr": completed.stderr.strip(),
    }


def summarize_eval_report(path: Path) -> dict[str, Any]:
    report = load_json(path)
    summary = report["summary"]
    payload: dict[str, Any] = {
        "report_path": relpath(path),
        "dataset_path": summary.get("dataset_path"),
        "summary": summary,
    }
    if "total_questions" in summary:
        payload["gate_status"] = bool(summary["successful_questions"] == summary["total_questions"])
    elif "total_pairs" in summary:
        payload["gate_status"] = bool(summary.get("benchmark_runner_blocker_count", 0) == 0)
    else:
        payload["gate_status"] = False
    return payload


def main() -> None:
    core_policy = load_json(CORE_POLICY_PATH)
    entrypoint_contract = load_json(ENTRYPOINT_CONTRACT_PATH)
    historical_registry = load_json(HISTORICAL_REGISTRY_PATH)
    processed_policy = load_json(PROCESSED_POLICY_PATH)
    documentation_report = load_json(DOCUMENTATION_REPORT_PATH)

    py_compile_result = run_py_compile()
    graphdb_healthcheck = run_graphdb_healthcheck()

    canonical_eval = summarize_eval_report(CANONICAL_REPORT_PATH)
    multihop_eval = summarize_eval_report(MULTIHOP_REPORT_PATH)
    quick_ref_eval = summarize_eval_report(QUICK_REF_REPORT_PATH)
    cross_eval = summarize_eval_report(CROSS_REPORT_PATH)

    canonical_ok = bool(canonical_eval["gate_status"])
    multihop_ok = bool(multihop_eval["gate_status"])
    quick_ref_ok = bool(quick_ref_eval["gate_status"])
    cross_ok = bool(cross_eval["gate_status"])
    baseline_ok = canonical_ok and multihop_ok and quick_ref_ok and cross_ok and py_compile_result["passed"]

    graphdb_stdout = graphdb_healthcheck.get("stdout") or {}
    graphdb_ok = bool(
        graphdb_healthcheck["passed"]
        and graphdb_stdout.get("status") == "repository_ready"
        and graphdb_stdout.get("server_available") is True
    )

    core_reusable_boundary_defined = bool(
        documentation_report["documentation_outcomes"]["core_reusable_boundary_documented"]
        and bool(core_policy["core_modules"])
    )
    project_specific_boundary_defined = bool(
        documentation_report["documentation_outcomes"]["project_specific_boundary_documented"]
        and bool(core_policy["project_specific_modules"])
    )
    stable_entrypoint_contract_defined = bool(
        entrypoint_contract["runtime_rebuild_entrypoint"]["path"] == "run_runtime_clean_rebuild.py"
        and documentation_report["documentation_outcomes"]["stable_rebuild_entrypoint_documented"]
        == "run_runtime_clean_rebuild.py"
    )
    historical_tooling_declassified = bool(
        core_policy["historical_tooling_declassified_from_operational_path"]
        and entrypoint_contract["historical_tooling_declassified_from_operational_path"]
        and documentation_report["documentation_outcomes"]["historical_tooling_declassified_from_operational_path"]
        and historical_registry["historical_tooling_declassified_from_operational_path"]
    )
    historical_tooling_isolated = False
    processed_artifact_policy_defined = bool(
        processed_policy["processed_namespace_policy"]["rebuild_category_a_from_scratch"]
        and documentation_report["documentation_outcomes"]["processed_artifact_policy_documented"]
    )

    ready_to_proceed_to_t27b = bool(
        core_reusable_boundary_defined
        and project_specific_boundary_defined
        and stable_entrypoint_contract_defined
        and historical_tooling_declassified
        and processed_artifact_policy_defined
        and baseline_ok
        and graphdb_ok
    )
    repo_ready_for_reuse = False
    repo_ready_for_case_specific_split = False

    cleanup_report = {
        "task": "T27A-006",
        "report_version": 1,
        "generated_from": "misc/coding-team/repo-reusability-core-split/generate_t27a_validation_and_decision.py",
        "source_artifacts": [
            relpath(CORE_POLICY_PATH),
            relpath(ENTRYPOINT_CONTRACT_PATH),
            relpath(HISTORICAL_REGISTRY_PATH),
            relpath(PROCESSED_POLICY_PATH),
            relpath(DOCUMENTATION_REPORT_PATH),
            relpath(CANONICAL_REPORT_PATH),
            relpath(MULTIHOP_REPORT_PATH),
            relpath(QUICK_REF_REPORT_PATH),
            relpath(CROSS_REPORT_PATH),
        ],
        "validation_results": {
            "py_compile": py_compile_result,
            "qa_canonical": canonical_eval,
            "qa_multihop": multihop_eval,
            "qa_8070_quick_ref_bilingual_v2": quick_ref_eval,
            "qa_cross": cross_eval,
            "graphdb_healthcheck": graphdb_healthcheck,
        },
        "criteria_status": {
            "core_reusable_boundary_defined": core_reusable_boundary_defined,
            "project_specific_boundary_defined": project_specific_boundary_defined,
            "stable_entrypoint_contract_defined": stable_entrypoint_contract_defined,
            "historical_tooling_declassified_from_operational_path": historical_tooling_declassified,
            "historical_tooling_isolated": historical_tooling_isolated,
            "processed_artifact_policy_defined": processed_artifact_policy_defined,
            "baseline_ok": baseline_ok,
            "graphdb_ok": graphdb_ok,
            "ready_to_proceed_to_t27b": ready_to_proceed_to_t27b,
        },
        "notes": [
            "T27A closes the contractual and documentation layer only; it does not claim structural isolation of historical tooling.",
            "Quick-ref and cross remain green under the current operational gate used by this repository: benchmark_runner_blocker_count = 0.",
            "repo_ready_for_reuse and repo_ready_for_case_specific_split stay false in T27A because those outcomes depend on T27B structural isolation work.",
        ],
    }

    decision_report = {
        "task": "T27A-006",
        "decision_version": 1,
        "source_cleanup_report": relpath(CLEANUP_REPORT_PATH),
        "core_reusable_boundary_defined": core_reusable_boundary_defined,
        "project_specific_boundary_defined": project_specific_boundary_defined,
        "stable_entrypoint_contract_defined": stable_entrypoint_contract_defined,
        "historical_tooling_declassified_from_operational_path": historical_tooling_declassified,
        "historical_tooling_isolated": historical_tooling_isolated,
        "processed_artifact_policy_defined": processed_artifact_policy_defined,
        "baseline_ok": baseline_ok,
        "graphdb_ok": graphdb_ok,
        "repo_ready_for_reuse": repo_ready_for_reuse,
        "repo_ready_for_case_specific_split": repo_ready_for_case_specific_split,
        "ready_to_proceed_to_t27b": ready_to_proceed_to_t27b,
        "recommended_next_step": (
            "start_t27b_structural_isolation"
            if ready_to_proceed_to_t27b
            else "resolve_t27a_validation_blockers"
        ),
        "notes": [
            "T27A is green when the contractual/documentary boundary is defined and the existing runtime remains healthy.",
            "Physical isolation of historical tooling and project-specific structure is deferred to T27B.",
        ],
    }

    CLEANUP_REPORT_PATH.write_text(json.dumps(cleanup_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DECISION_REPORT_PATH.write_text(json.dumps(decision_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
