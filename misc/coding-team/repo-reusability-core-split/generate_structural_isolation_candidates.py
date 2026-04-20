from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

INVENTORY_PATH = PROCESSED_DIR / "t27_repo_reusability_inventory.json"
POLICY_PATH = PROCESSED_DIR / "t27_core_vs_project_policy.json"
ENTRYPOINT_CONTRACT_PATH = PROCESSED_DIR / "t27_stable_entrypoint_contract.json"
PROCESSED_POLICY_PATH = PROCESSED_DIR / "t27_processed_artifact_policy.json"
PROCESSED_REGISTRY_PATH = PROCESSED_DIR / "t27_processed_artifact_registry.json"
DECISION_PATH = PROCESSED_DIR / "t27_repo_cleanup_decision_report.json"
OUTPUT_PATH = PROCESSED_DIR / "t27_repo_structure_refactor_report.json"


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


def record(
    index: dict[str, dict[str, Any]],
    path: str,
    *,
    disposition: str,
    suggested_grouping_area: str,
    risk_level: str,
    recommended_next_step: str,
    why: str,
    compatibility_notes: str,
) -> dict[str, Any]:
    item = require_entry(index, path)
    return {
        "path": path,
        "type": item["type"],
        "current_category": item["category"],
        "runtime_critical": item["runtime_critical"],
        "project_specific": item["project_specific"],
        "current_recommended_action": item["recommended_action"],
        "disposition": disposition,
        "suggested_grouping_area": suggested_grouping_area,
        "risk_level": risk_level,
        "recommended_next_step": recommended_next_step,
        "why": why,
        "compatibility_notes": compatibility_notes,
        "notes": item["notes"],
    }


def sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: record["path"])


def main() -> None:
    inventory = load_json(INVENTORY_PATH)
    policy = load_json(POLICY_PATH)
    entrypoint_contract = load_json(ENTRYPOINT_CONTRACT_PATH)
    processed_policy = load_json(PROCESSED_POLICY_PATH)
    processed_registry = load_json(PROCESSED_REGISTRY_PATH)
    decision = load_json(DECISION_PATH)

    index = build_index(inventory["items"])

    if not decision["ready_to_proceed_to_t27b"]:
        raise RuntimeError("T27B cannot start before T27A is ready_to_proceed_to_t27b.")

    safe_to_isolate_now = sort_records(
        [
            record(
                index,
                path,
                disposition="safe-to-isolate-now",
                suggested_grouping_area="history/tooling/",
                risk_level="low",
                recommended_next_step="move_or_group_under_explicit_historical_tooling_area_with_compatibility_stub_if_needed",
                why=(
                    "This path is already declassified from the operational primary path and has no "
                    "runtime-critical role in the active rebuild, publish, or query contract."
                ),
                compatibility_notes=(
                    "Movement is low risk because the stable entrypoint contract already excludes it from "
                    "the operational path; only traceability links or documentation references need care."
                ),
            )
            for path in require_paths(index, list(policy["historical_wrappers"]))
        ]
        + [
            record(
                index,
                "check_mistral_api_usage.py",
                disposition="safe-to-isolate-now",
                suggested_grouping_area="history/tooling/diagnostics/",
                risk_level="low",
                recommended_next_step="group_with_diagnostic_or_historical_tooling_without_presenting_it_as_runtime_contract",
                why=(
                    "This script is a smoke-test utility for provider availability and is not part of the "
                    "runtime rebuild or GraphDB contract."
                ),
                compatibility_notes=(
                    "No runtime imports depend on it. If moved later, a lightweight shim or updated docs "
                    "would be sufficient."
                ),
            )
        ]
    )

    keep_in_place_but_reclassify = sort_records(
        [
            record(
                index,
                "run_operational_pipeline.py",
                disposition="keep-in-place-but-reclassify",
                suggested_grouping_area="stable-entrypoints/supporting/",
                risk_level="medium",
                recommended_next_step="keep_at_root_as_supported_operational_entrypoint_but_document_it_as_secondary_to_clean_rebuild",
                why=(
                    "It is still part of the stable operational contract, but it is no longer the primary "
                    "full-runtime rebuild path."
                ),
                compatibility_notes=(
                    "Moving it now would ripple through documentation and operator habits without enough "
                    "architectural value for T27B."
                ),
            ),
            record(
                index,
                "src/8_retrieval/text_to_sparql.py",
                disposition="keep-in-place-but-reclassify",
                suggested_grouping_area="src/8_retrieval/ (project-config-heavy boundary)",
                risk_level="high",
                recommended_next_step="retain_in_place_and make_project_coupling_explicit_in_docs_and_future_split_registry",
                why=(
                    "The planner core is reusable, but the current family catalog is deeply coupled to the "
                    "broaching/CNC project and still drives live runtime behavior."
                ),
                compatibility_notes=(
                    "Physical movement now would force broad import and test updates across the retrieval layer."
                ),
            ),
            record(
                index,
                "src/8_retrieval/multilingual_query_normalizer.py",
                disposition="keep-in-place-but-reclassify",
                suggested_grouping_area="src/8_retrieval/ (project-config-heavy boundary)",
                risk_level="high",
                recommended_next_step="retain_in_place_and document_as_project-tuned_runtime_module",
                why=(
                    "Normalization and anchor collision handling are still tuned against the current project corpus."
                ),
                compatibility_notes=(
                    "Moving it before a broader retrieval config split would create more churn than isolation value."
                ),
            ),
            record(
                index,
                "src/8_retrieval/synthesis_pipeline.py",
                disposition="keep-in-place-but-reclassify",
                suggested_grouping_area="src/8_retrieval/ (project-config-heavy boundary)",
                risk_level="high",
                recommended_next_step="retain_in_place_and document_as project-tuned answer shaping",
                why=(
                    "The synthesis scaffolding is reusable, but current answer shaping remains tuned to project QA gates."
                ),
                compatibility_notes=(
                    "Movement now would not reduce coupling because retrieval and evaluation still invoke it directly."
                ),
            ),
            record(
                index,
                "cache/terms_cache.json",
                disposition="keep-in-place-but-reclassify",
                suggested_grouping_area="project-input-cache/",
                risk_level="medium",
                recommended_next_step="retain_current_path_for_compatibility_and classify_as_project-specific cache",
                why=(
                    "The cache content is derived from the accepted project corpus, but current ingestion scripts "
                    "and rebuild expectations still assume the existing path."
                ),
                compatibility_notes=(
                    "A move should wait until project-specific input spaces are encapsulated more explicitly in Task 009."
                ),
            ),
            record(
                index,
                "data/raw/density_report.json",
                disposition="keep-in-place-but-reclassify",
                suggested_grouping_area="project-default-inputs/legacy/",
                risk_level="medium",
                recommended_next_step="retain_as legacy default density input and keep it out of the clean rebuild primary path",
                why=(
                    "It remains useful for compatibility with the default single-path build, but it no longer "
                    "represents the accepted multi-manual rebuild contract."
                ),
                compatibility_notes=(
                    "Moving it now could break lower-level build assumptions without helping the reusable boundary much."
                ),
            ),
        ]
    )

    already_classified = {
        record["path"] for record in safe_to_isolate_now + keep_in_place_but_reclassify
    }

    defer_to_future_project_repo = sort_records(
        [
            record(
                index,
                path,
                disposition="defer-to-future-project-repo",
                suggested_grouping_area="future-project-repo/",
                risk_level="medium",
                recommended_next_step="keep_rebuildable_in_place_now_but mark_as project-owned migration candidate",
                why=(
                    "This path belongs to the current broaching/CNC project scope and should ultimately move "
                    "with the case-specific repository once the split is executed."
                ),
                compatibility_notes=(
                    "It remains in-repo for accepted-project rebuildability, so T27B should only classify and "
                    "surface the boundary rather than move it now."
                ),
            )
            for path in require_paths(index, list(policy["future_project_repo_candidates"]))
            if path not in already_classified
        ]
    )

    archive_later = sort_records(
        [
            record(
                index,
                path,
                disposition="archive-later",
                suggested_grouping_area="history/archive/",
                risk_level="low" if not require_entry(index, path)["runtime_critical"] else "medium",
                recommended_next_step="retain_visible_for_traceability_now_and archive_or regroup only after T27B compatibility work is green",
                why=(
                    "This path is already outside the live runtime contract or should not define runtime inputs, "
                    "but preserving traceability remains more valuable than immediate movement."
                ),
                compatibility_notes=(
                    "These paths should be grouped after the stable/historical boundary is clearer, to avoid "
                    "mixing archival cleanup with the first isolation wave."
                ),
            )
            for path in require_paths(
                index,
                [
                    "src/2_extraction/",
                    "src/3_merging/",
                    "src/5_alignment/",
                    "codes_endika/",
                    "data/raw/Chunks/1000/",
                    "data/processed/t21_* through data/processed/t26_*",
                    "data/processed/runtime_clean_rebuild_preflight.json and data/processed/runtime_clean_rebuild_report.json",
                    "data/processed/runtime_non_operational_inventory.json and data/processed/runtime_cleanup_second_pass_report.json",
                    "data/processed/*debug*.json, data/processed/qa_failure_analysis.json, data/processed/query_debug_report.json, data/processed/synthesis_debug_report.json",
                    "data/processed/*_abox_debug/",
                ],
            )
        ]
    )

    report = {
        "task": "T27B-007",
        "report_version": 1,
        "generated_from": "misc/coding-team/repo-reusability-core-split/generate_structural_isolation_candidates.py",
        "source_of_truth": {
            "inventory": str(INVENTORY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            "core_vs_project_policy": str(POLICY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            "stable_entrypoint_contract": str(ENTRYPOINT_CONTRACT_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            "processed_artifact_policy": str(PROCESSED_POLICY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            "processed_artifact_registry": str(PROCESSED_REGISTRY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            "t27a_decision": str(DECISION_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        },
        "t27b_starting_state": {
            "ready_to_proceed_to_t27b": bool(decision["ready_to_proceed_to_t27b"]),
            "baseline_ok": bool(decision["baseline_ok"]),
            "graphdb_ok": bool(decision["graphdb_ok"]),
            "runtime_rebuild_entrypoint": entrypoint_contract["runtime_rebuild_entrypoint"]["path"],
            "historical_tooling_declassified_from_operational_path": bool(
                entrypoint_contract["historical_tooling_declassified_from_operational_path"]
            ),
        },
        "evaluation_principles": [
            "Prefer semantic or documentary isolation over physical moves when a move would force broad path rewrites.",
            "Do not move runtime-critical modules in the first isolation wave.",
            "Use the stable entrypoint contract as the guardrail for what must remain easy to find and runnable.",
            "Keep accepted project inputs rebuildable from this repository until the case-specific split is executed.",
        ],
        "disposition_counts": {
            "safe-to-isolate-now": len(safe_to_isolate_now),
            "keep-in-place-but-reclassify": len(keep_in_place_but_reclassify),
            "defer-to-future-project-repo": len(defer_to_future_project_repo),
            "archive-later": len(archive_later),
        },
        "safe-to-isolate-now": safe_to_isolate_now,
        "keep-in-place-but-reclassify": keep_in_place_but_reclassify,
        "defer-to-future-project-repo": defer_to_future_project_repo,
        "archive-later": archive_later,
        "t27b_task_sequencing": {
            "task_008_focus": [
                record["path"] for record in safe_to_isolate_now
            ],
            "task_009_focus": [
                "cache/terms_cache.json",
                "data/raw/",
                "data/golden_set/",
                "data/processed/a218_*",
                "data/processed/quick_ref_*",
                "data/processed/installation_manual_* and data/processed/8070_installation_*",
                "data/processed/man_8070_err_*",
            ],
            "do_not_move_during_t27b_without_new_architectural_decision": [
                "run_runtime_clean_rebuild.py",
                "run_operational_pipeline.py",
                "src/6_extraction/",
                "src/7_database/",
                "src/8_retrieval/text_to_sparql.py",
                "src/8_retrieval/multilingual_query_normalizer.py",
                "src/8_retrieval/synthesis_pipeline.py",
                "data/processed/ontology_aligned.ttl",
                "data/processed/abox_linked.ttl",
            ],
        },
        "compatibility_notes": [
            "The first T27B move wave should target only historical wrappers and clearly non-operational planning/diagnostic utilities.",
            "Project-specific retrieval modules should be made explicit as project-tuned boundaries before any physical split is attempted.",
            "Accepted project corpus inputs remain in-repo for rebuildability and therefore belong to Task 009 classification work, not immediate movement in Task 007.",
            "Legacy experimental tracks and historical processed outputs are better grouped into archival areas after historical tooling isolation is already clear.",
        ],
        "processed_policy_context": {
            "processed_item_count": processed_policy["registry_summary"]["processed_item_count"],
            "counts_by_policy_group": processed_policy["registry_summary"]["counts_by_policy_group"],
            "allowed_processed_inputs_for_clean_rebuild": processed_policy["authoritative_input_rules"][
                "allowed_processed_inputs_for_clean_rebuild"
            ],
        },
    }

    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
