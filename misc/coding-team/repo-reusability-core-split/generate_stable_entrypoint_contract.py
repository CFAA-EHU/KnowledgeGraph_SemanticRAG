from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = REPO_ROOT / "data" / "processed" / "t27_repo_reusability_inventory.json"
POLICY_PATH = REPO_ROOT / "data" / "processed" / "t27_core_vs_project_policy.json"
CONTRACT_OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "t27_stable_entrypoint_contract.json"
REGISTRY_OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "t27_historical_tooling_registry.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["path"]): item for item in items}


def require_paths(index: dict[str, dict[str, Any]], paths: list[str]) -> list[str]:
    missing = [path for path in paths if path not in index]
    if missing:
        raise KeyError(f"Missing inventory paths: {missing}")
    return paths


def require_entry(index: dict[str, dict[str, Any]], path: str) -> dict[str, Any]:
    if path not in index:
        raise KeyError(f"Missing inventory path: {path}")
    return index[path]


def historical_record(index: dict[str, dict[str, Any]], path: str, *, kind: str, rationale: str) -> dict[str, Any]:
    item = require_entry(index, path)
    return {
        "path": path,
        "kind": kind,
        "inventory_category": item["category"],
        "runtime_critical": item["runtime_critical"],
        "project_specific": item["project_specific"],
        "recommended_action": item["recommended_action"],
        "declassified_from_operational_path": True,
        "doc_visibility": "historical_or_diagnostic_only",
        "rationale": rationale,
        "notes": item["notes"],
    }


def main() -> None:
    inventory = load_json(INVENTORY_PATH)
    policy = load_json(POLICY_PATH)
    items = inventory["items"]
    index = build_index(items)

    official_runtime_rebuild = require_paths(index, ["run_runtime_clean_rebuild.py"])[0]
    supporting_runtime_entrypoint = require_paths(index, ["run_operational_pipeline.py"])[0]
    graphdb_publish = require_paths(index, ["src/7_database/publish_to_graphdb.py"])[0]
    graphdb_healthcheck = require_paths(index, ["src/7_database/graphdb_healthcheck.py"])[0]
    evaluator = require_paths(index, ["src/8_retrieval/qa_evaluator.py"])[0]
    query_entrypoint = require_paths(index, ["query_workbench.py"])[0]

    evaluation_gate_datasets = require_paths(
        index,
        [
            "data/golden_set/QA_canonical.json",
            "data/golden_set/QA_multihop.json",
            "data/golden_set/QA_8070_quick_ref_bilingual_v2.json",
            "data/golden_set/QA_cross.json",
        ],
    )

    supported_manifests = {
        "accepted_runtime_manual_set": {
            "manifest_type": "embedded_manual_spec_set",
            "owner_entrypoint": official_runtime_rebuild,
            "location": "run_runtime_clean_rebuild.py:ACCEPTED_MANUALS",
            "status": "supported",
            "notes": (
                "The current clean rebuild contract uses an embedded accepted-manual set rather than an "
                "external JSON manifest. This is the supported rebuild manifest for the live runtime."
            ),
        },
        "single_manual_onboarding_profile": {
            "manifest_type": "derived_manual_profile",
            "owner_entrypoint": supporting_runtime_entrypoint,
            "location": "artifact_contracts.build_onboarding_profile()",
            "status": "supported_for_onboarding_only",
            "notes": (
                "Single-manual onboarding remains a supported operational capability, but it is not the "
                "primary rebuild contract for the full runtime."
            ),
        },
        "external_rebuild_manifest": {
            "manifest_type": "external_json_manifest",
            "owner_entrypoint": official_runtime_rebuild,
            "status": "not_yet_supported",
            "notes": (
                "No standalone source-manifest file is part of the stable runtime contract yet. The rebuild "
                "entrypoint currently owns the accepted manual set directly."
            ),
        },
    }

    contract = {
        "task": "T27A-003",
        "contract_version": 1,
        "generated_from": "misc/coding-team/repo-reusability-core-split/generate_stable_entrypoint_contract.py",
        "source_inventory": str(INVENTORY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "source_policy": str(POLICY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "historical_tooling_declassified_from_operational_path": bool(
            policy["historical_tooling_declassified_from_operational_path"]
        ),
        "runtime_rebuild_entrypoint": {
            "path": official_runtime_rebuild,
            "classification": "official_primary",
            "supported_scope": "clean_multi_manual_runtime_rebuild_for_accepted_manuals",
            "why_primary": (
                "It is the only entrypoint that rebuilds the accepted runtime scope end-to-end under a "
                "single explicit contract, including validation and optional GraphDB publication."
            ),
            "invocation_example": "python run_runtime_clean_rebuild.py --mode resume-compatible",
            "supported_options": {
                "mode": ["resume-compatible", "force-stale", "force-all"],
                "retry_profile": ["standard", "rate-limit-drain", "micro-batch-recovery"],
                "skip_publish": True,
            },
        },
        "supporting_operational_entrypoints": [
            {
                "path": supporting_runtime_entrypoint,
                "classification": "stable_supporting_entrypoint",
                "supported_scope": "default_runtime_build_and_single_manual_onboarding",
                "why_not_primary": (
                    "It remains a stable operational script, but its contract is narrower and more tactical "
                    "than the clean multi-manual rebuild path."
                ),
                "invocation_examples": [
                    "python run_operational_pipeline.py --mode resume-compatible",
                    (
                        "python run_operational_pipeline.py --source-chunks data/raw/chunks_8070_quick_ref.txt "
                        "--manual-id 8070_quick_ref --mode resume-compatible"
                    ),
                ],
            }
        ],
        "graphdb_publish_entrypoint": {
            "path": graphdb_publish,
            "classification": "official_primary",
            "supported_scope": "publish_current_runtime_mirror",
            "invocation_example": "python src/7_database/publish_to_graphdb.py",
        },
        "graphdb_healthcheck_entrypoint": {
            "path": graphdb_healthcheck,
            "classification": "official_primary",
            "supported_scope": "healthcheck_current_runtime_mirror",
            "invocation_example": "python src/7_database/graphdb_healthcheck.py",
        },
        "evaluation_entrypoints": [
            {
                "path": evaluator,
                "classification": "official_primary",
                "supported_scope": "baseline_and_project_gate_evaluation",
                "required_gate_datasets": evaluation_gate_datasets,
                "examples": [
                    "python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_canonical.json",
                    "python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json",
                    (
                        "python src/8_retrieval/qa_evaluator.py --qa-file "
                        "data/golden_set/QA_8070_quick_ref_bilingual_v2.json"
                    ),
                    "python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_cross.json",
                ],
            }
        ],
        "query_entrypoints": [
            {
                "path": query_entrypoint,
                "classification": "official_primary_for_manual_queries",
                "supported_scope": "planner_retrieval_and_synthesis_queries",
                "invocation_example": 'python query_workbench.py "Que directiva cumple la maquina?" --backend rdflib',
            }
        ],
        "supported_manifests": supported_manifests,
        "non_primary_but_retained": {
            "historical_wrappers": policy["historical_wrappers"],
            "diagnostic_utility_scripts": require_paths(index, ["check_mistral_api_usage.py"]),
        },
        "notes": [
            "Documentation should point to one runtime rebuild path only: run_runtime_clean_rebuild.py.",
            "Historical campaign wrappers remain traceable but must not be documented as normal rebuild entrypoints.",
            "run_operational_pipeline.py remains supported as a lower-level operational and onboarding script, not the primary full-runtime rebuild contract.",
        ],
    }

    historical_registry = {
        "task": "T27A-003",
        "registry_version": 1,
        "generated_from": "misc/coding-team/repo-reusability-core-split/generate_stable_entrypoint_contract.py",
        "source_inventory": str(INVENTORY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "source_policy": str(POLICY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "historical_tooling_declassified_from_operational_path": bool(
            policy["historical_tooling_declassified_from_operational_path"]
        ),
        "registry": [
            historical_record(
                index,
                "run_t25_sequential_integration.py",
                kind="historical_wrapper",
                rationale="Campaign-specific sequential integration flow for T25; preserved for traceability only.",
            ),
            historical_record(
                index,
                "run_t25_2_installation_recovery.py",
                kind="historical_wrapper",
                rationale="Task-specific installation recovery flow; not part of the steady-state rebuild contract.",
            ),
            historical_record(
                index,
                "run_t26_error_manual_onboarding.py",
                kind="historical_wrapper",
                rationale="Task-specific onboarding flow for the error manual; preserved as campaign history.",
            ),
            historical_record(
                index,
                "docs/runtime_clean_rebuild_plan.md",
                kind="transition_planning_document",
                rationale="Transition planning document that informed the current rebuild contract, but is not itself an entrypoint.",
            ),
            historical_record(
                index,
                "misc/coding-team/repo-reusability-core-split/",
                kind="architect_traceability",
                rationale="Architect planning and task-brief traceability for T27, not runtime tooling.",
            ),
            {
                "path": "check_mistral_api_usage.py",
                "kind": "diagnostic_utility",
                "inventory_category": require_entry(index, "check_mistral_api_usage.py")["category"],
                "runtime_critical": False,
                "project_specific": False,
                "recommended_action": require_entry(index, "check_mistral_api_usage.py")["recommended_action"],
                "declassified_from_operational_path": True,
                "doc_visibility": "diagnostic_only",
                "rationale": (
                    "Useful for provider smoke tests and rate-limit diagnostics, but it must never appear as "
                    "a normal runtime rebuild or publication path."
                ),
                "notes": require_entry(index, "check_mistral_api_usage.py")["notes"],
            },
        ],
        "notes": [
            "Registry entries remain in the repository for traceability, diagnostics, or planning history.",
            "None of these entries should be documented as the primary runtime rebuild path after T27A.",
        ],
    }

    CONTRACT_OUTPUT_PATH.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REGISTRY_OUTPUT_PATH.write_text(json.dumps(historical_registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
