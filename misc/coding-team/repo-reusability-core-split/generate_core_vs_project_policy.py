from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = REPO_ROOT / "data" / "processed" / "t27_repo_reusability_inventory.json"
OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "t27_core_vs_project_policy.json"


def load_inventory() -> dict[str, Any]:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def build_index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["path"]): item for item in items}


def require_paths(index: dict[str, dict[str, Any]], paths: list[str]) -> list[str]:
    missing = [path for path in paths if path not in index]
    if missing:
        raise KeyError(f"Missing inventory paths: {missing}")
    return paths


def unique_ordered(values: list[str]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        if value not in ordered:
            ordered.append(value)
    return ordered


def main() -> None:
    inventory = load_inventory()
    items = inventory["items"]
    index = build_index(items)

    core_modules = {
        "shared_contract_and_operational_docs": require_paths(
            index,
            [
                "artifact_contracts.py",
                "README.md",
                "docs/README.md",
                "docs/operational_artifact_contract.md",
                "docs/operational_pipeline_runbook.md",
            ],
        ),
        "ingestion_layer": require_paths(
            index,
            [
                "src/1_ingestion/",
                "src/1_ingestion/density_analyzer.py",
                "src/1_ingestion/termLoader.py",
            ],
        ),
        "runtime_build_layer": require_paths(
            index,
            [
                "src/6_extraction/",
                "src/6_extraction/abox_input_builder.py",
                "src/6_extraction/abox_extractor.py",
                "src/6_extraction/abox_merger.py",
                "src/6_extraction/abox_canonicalizer.py",
                "src/6_extraction/abox_graph_enricher.py",
                "src/6_extraction/abox_link_completer.py",
                "src/6_extraction/abox_resume_policy.py",
                "src/6_extraction/canonical_resolution_policy.py",
                "src/6_extraction/enrichment_policy.py",
                "src/6_extraction/link_completion_policy.py",
            ],
        ),
        "runtime_backend_layer": require_paths(
            index,
            [
                "src/7_database/",
                "src/7_database/graph_store.py",
                "src/7_database/publish_to_graphdb.py",
                "src/7_database/graphdb_healthcheck.py",
            ],
        ),
        "runtime_retrieval_core": require_paths(
            index,
            [
                "src/8_retrieval/",
                "src/8_retrieval/multilingual_lexicon_builder.py",
                "src/8_retrieval/qa_evaluator.py",
                "query_workbench.py",
                "requirements.txt",
            ],
        ),
    }

    project_specific_modules = {
        "project_tuned_runtime_modules": require_paths(
            index,
            [
                "src/8_retrieval/text_to_sparql.py",
                "src/8_retrieval/multilingual_query_normalizer.py",
                "src/8_retrieval/synthesis_pipeline.py",
            ],
        ),
        "project_input_spaces": require_paths(
            index,
            [
                "data/raw/",
                "data/golden_set/",
                "cache/terms_cache.json",
            ],
        ),
        "accepted_manual_assets_retained_in_repo": require_paths(
            index,
            [
                "data/raw/chunks_manual_instrucciones_a218.txt",
                "data/raw/chunks_8070_quick_ref.txt",
                "data/raw/chunks_8070_installation_manual.txt",
                "data/raw/chunks_man_8070_err.txt",
                "data/processed/a218_*",
                "data/processed/quick_ref_*",
                "data/processed/installation_manual_* and data/processed/8070_installation_*",
                "data/processed/man_8070_err_*",
                "data/golden_set/QA_canonical.json",
                "data/golden_set/QA_multihop.json",
                "data/golden_set/QA_cross.json",
                "data/golden_set/QA_8070_quick_ref_bilingual_v2.json",
                "data/golden_set/QA_chunks_8070_installation_manual.json",
                "data/golden_set/QA_chunks_man_8070_err.json",
            ],
        ),
        "future_project_onboarding_candidates": require_paths(
            index,
            [
                "data/raw/chunks_8070_operating_programming_manual.txt",
                "data/raw/chunks_8070_programming_manual.txt",
                "data/raw/chunks_8070_remote_modules.txt",
                "data/raw/chunks_manual_variables_cnc_8070.txt",
                "data/raw/chunks_dds_soft.txt",
                "data/golden_set/QA_chunks_8070_operating_programming_manual.json",
                "data/golden_set/QA_chunks_8070_programming_manual.json",
                "data/golden_set/QA_chunks_8070_remote_modules.json",
                "data/golden_set/QA_chunks_manual_variables_cnc_8070.json",
                "data/golden_set/QA_chunks_dds_soft.json",
            ],
        ),
    }

    historical_wrappers = require_paths(
        index,
        [
            "run_t25_sequential_integration.py",
            "run_t25_2_installation_recovery.py",
            "run_t26_error_manual_onboarding.py",
            "docs/runtime_clean_rebuild_plan.md",
            "misc/coding-team/repo-reusability-core-split/",
        ],
    )

    stable_entrypoints = {
        "runtime_rebuild": require_paths(
            index,
            [
                "run_operational_pipeline.py",
                "run_runtime_clean_rebuild.py",
            ],
        ),
        "graphdb_publish": require_paths(index, ["src/7_database/publish_to_graphdb.py"])[0],
        "graphdb_healthcheck": require_paths(index, ["src/7_database/graphdb_healthcheck.py"])[0],
        "evaluation": require_paths(index, ["src/8_retrieval/qa_evaluator.py"]),
        "query": require_paths(index, ["query_workbench.py"]),
    }

    runtime_contract_artifacts = {
        "runtime_graph_contract": require_paths(
            index,
            [
                "data/processed/ontology_aligned.ttl",
                "data/processed/abox_input.json",
                "data/processed/abox_merged.ttl",
                "data/processed/abox_canonical.ttl",
                "data/processed/abox_enriched.ttl",
                "data/processed/abox_linked.ttl",
                "data/processed/multilingual_lexicon.json",
            ],
        ),
        "runtime_build_reports_and_maps": require_paths(
            index,
            [
                "data/processed/canonical_entity_map.json",
                "data/processed/canonicalization_report.json",
                "data/processed/canonicalization_resolution_candidates.json",
                "data/processed/enrichment_report.json",
                "data/processed/enrichment_link_map.json",
                "data/processed/enrichment_surface_map.json",
                "data/processed/link_completion_report.json",
                "data/processed/link_completion_map.json",
                "data/processed/link_completion_candidates.json",
                "data/processed/graphdb_publication_report.json",
            ],
        ),
        "runtime_operational_gates_for_current_project": require_paths(
            index,
            [
                "data/processed/generalization_eval_report.json",
                "data/processed/multihop_eval_report.json",
                "data/processed/quick_ref_v2_eval_report.json",
                "data/processed/cross_eval_report.json",
            ],
        ),
        "contract_docs": require_paths(
            index,
            [
                "docs/operational_artifact_contract.md",
                "docs/operational_pipeline_runbook.md",
            ],
        ),
    }

    future_project_repo_candidates = unique_ordered(
        project_specific_modules["project_input_spaces"]
        + project_specific_modules["accepted_manual_assets_retained_in_repo"]
        + project_specific_modules["future_project_onboarding_candidates"]
        + project_specific_modules["project_tuned_runtime_modules"]
    )

    archival_policy = {
        "retain_in_repo_but_declassified_from_operational_path": historical_wrappers,
        "retain_as_historical_campaign_traceability": require_paths(
            index,
            [
                "data/processed/t21_* through data/processed/t26_*",
                "data/processed/runtime_clean_rebuild_preflight.json and data/processed/runtime_clean_rebuild_report.json",
                "data/processed/runtime_non_operational_inventory.json and data/processed/runtime_cleanup_second_pass_report.json",
            ],
        ),
        "retain_as_legacy_experimental_tracks": require_paths(
            index,
            [
                "src/2_extraction/",
                "src/3_merging/",
                "src/5_alignment/",
            ],
        ),
        "preserve_now_archive_later": require_paths(
            index,
            [
                "codes_endika/",
                "data/raw/Chunks/1000/",
            ],
        ),
        "must_not_define_runtime_inputs": unique_ordered(
            historical_wrappers
            + require_paths(
                index,
                [
                    "data/processed/t21_* through data/processed/t26_*",
                    "data/processed/runtime_non_operational_inventory.json and data/processed/runtime_cleanup_second_pass_report.json",
                    "data/processed/*debug*.json, data/processed/qa_failure_analysis.json, data/processed/query_debug_report.json, data/processed/synthesis_debug_report.json",
                ],
            )
        ),
    }

    policy = {
        "task": "T27A-002",
        "policy_version": 1,
        "generated_from": "misc/coding-team/repo-reusability-core-split/generate_core_vs_project_policy.py",
        "source_inventory": "data/processed/t27_repo_reusability_inventory.json",
        "historical_tooling_declassified_from_operational_path": True,
        "inventory_summary": {
            "item_count": inventory["item_count"],
            "counts_by_category": inventory["counts_by_category"],
        },
        "policy_statement": {
            "core_definition": (
                "The reusable repository core is the ingestion, operational A-Box build, "
                "runtime backend, retrieval scaffolding, and contract documentation needed "
                "to rebuild, publish, query, and validate a runtime graph independently of "
                "the current broaching/CNC manual corpus."
            ),
            "project_definition": (
                "Project-specific scope includes the current manual corpus, accepted-manual "
                "onboarding assets, golden sets, current QA gates, and retrieval tuning that "
                "encodes the broaching/CNC domain."
            ),
            "compatibility_rule": (
                "T27A policy is contractual only. It must preserve the current runtime by "
                "reclassifying assets and tooling without moving files or changing imports."
            ),
            "accepted_manual_rule": (
                "Accepted manual assets and golden sets remain in-repo for compatibility and "
                "rebuildability, but they are project-specific and future candidates for the "
                "broaching use-case repository."
            ),
        },
        "core_modules": core_modules,
        "project_specific_modules": project_specific_modules,
        "historical_wrappers": historical_wrappers,
        "stable_entrypoints": stable_entrypoints,
        "runtime_contract_artifacts": runtime_contract_artifacts,
        "future_project_repo_candidates": future_project_repo_candidates,
        "archival_policy": archival_policy,
    }

    OUTPUT_PATH.write_text(
        json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
