from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
PROJECTS_DIR = REPO_ROOT / "projects"
PROJECT_DIR = PROJECTS_DIR / "broaching-cnc-8070"
PROJECT_MANIFEST_PATH = PROJECT_DIR / "project_scope_manifest.json"
BOUNDARY_REGISTRY_PATH = PROCESSED_DIR / "t27_project_specific_boundary_registry.json"
CORE_POLICY_PATH = PROCESSED_DIR / "t27_core_vs_project_policy.json"
PROCESSED_POLICY_PATH = PROCESSED_DIR / "t27_processed_artifact_policy.json"
PROCESSED_REGISTRY_PATH = PROCESSED_DIR / "t27_processed_artifact_registry.json"
STRUCTURE_REPORT_PATH = PROCESSED_DIR / "t27_repo_structure_refactor_report.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def build_project_manifest(
    core_policy: dict,
    processed_registry: dict,
) -> dict:
    accepted_processed_groups = [
        entry["path"]
        for entry in processed_registry["registry"]
        if entry.get("policy_group") == "accepted_project_operational_artifact"
    ]
    current_project_gates = [
        "data/golden_set/QA_canonical.json",
        "data/golden_set/QA_multihop.json",
        "data/golden_set/QA_cross.json",
        "data/golden_set/QA_8070_quick_ref_bilingual_v2.json",
    ]
    return {
        "project_id": "broaching-cnc-8070-reference",
        "project_grouping_area": "projects/broaching-cnc-8070/",
        "manifest_purpose": (
            "Make the retained broaching/CNC 8070 reference scope explicit without moving "
            "live runtime inputs or breaking current rebuildability."
        ),
        "status": "retained_in_core_repo_for_compatibility_and_future_split_preparation",
        "future_target": "new_broaching_use_case_repository",
        "current_live_paths_retained_in_place": {
            "source_manual_space": "data/raw/",
            "golden_set_space": "data/golden_set/",
            "shared_terms_cache": "cache/terms_cache.json",
            "accepted_processed_artifact_groups": accepted_processed_groups,
        },
        "accepted_runtime_scope": {
            "source_manuals": [
                "data/raw/chunks_manual_instrucciones_a218.txt",
                "data/raw/chunks_8070_quick_ref.txt",
                "data/raw/chunks_8070_installation_manual.txt",
                "data/raw/chunks_man_8070_err.txt",
            ],
            "golden_sets_and_current_gates": current_project_gates
            + [
                "data/golden_set/QA_chunks_8070_installation_manual.json",
                "data/golden_set/QA_chunks_man_8070_err.json",
            ],
            "project_tuned_runtime_modules": core_policy["project_specific_modules"][
                "project_tuned_runtime_modules"
            ],
        },
        "future_project_onboarding_candidates": core_policy["project_specific_modules"][
            "future_project_onboarding_candidates"
        ],
        "compatibility_rules": [
            "Do not move data/raw, data/golden_set, or accepted manual-specific processed artifacts during T27B.",
            "Use this grouping area as the canonical boundary marker while live paths remain unchanged.",
            "Treat project-tuned retrieval modules as retained-in-place until a later planner/retrieval config split exists.",
        ],
        "notes": [
            "This manifest is documentary and contractual. It does not replace the current live paths.",
            "The future split should move the project scope represented here into a dedicated repository once the reusable core is fully separated.",
        ],
    }


def build_boundary_registry(
    core_policy: dict,
    processed_policy: dict,
    processed_registry: dict,
    structure_report: dict,
) -> dict:
    accepted_processed_groups = [
        {
            "path": entry["path"],
            "policy_group": entry["policy_group"],
            "recommended_action": entry["recommended_action"],
            "authoritative_for_clean_rebuild_input": entry["authoritative_for_clean_rebuild_input"],
        }
        for entry in processed_registry["registry"]
        if entry.get("policy_group") == "accepted_project_operational_artifact"
    ]
    retrieval_couplings = [
        item
        for item in structure_report.get("keep-in-place-but-reclassify", [])
        if str(item.get("path", "")).startswith("src/8_retrieval/")
    ]
    return {
        "task": "T27B-009",
        "report_version": 1,
        "generated_from": "misc/coding-team/repo-reusability-core-split/generate_project_specific_boundary.py",
        "source_of_truth": {
            "core_vs_project_policy": "data/processed/t27_core_vs_project_policy.json",
            "processed_artifact_policy": "data/processed/t27_processed_artifact_policy.json",
            "processed_artifact_registry": "data/processed/t27_processed_artifact_registry.json",
            "repo_structure_refactor_report": "data/processed/t27_repo_structure_refactor_report.json",
        },
        "project_grouping_area": {
            "path": "projects/broaching-cnc-8070/",
            "manifest": "projects/broaching-cnc-8070/project_scope_manifest.json",
            "status": "canonical_grouping_area_for_project_specific_boundary",
            "move_policy": "group_and_document_without_moving_live_paths",
        },
        "explicit_boundary_actions": [
            "Created a canonical grouping area for the retained broaching/CNC 8070 reference project.",
            "Created a project scope manifest that points to the current live paths instead of relocating them.",
            "Recorded accepted project processed artifacts and current project gates as project-owned compatibility inputs.",
            "Made retained retrieval/planner coupling visible as project-tuned runtime modules kept in place for compatibility.",
        ],
        "retained_in_place_for_compatibility": {
            "project_input_spaces": core_policy["project_specific_modules"]["project_input_spaces"],
            "accepted_manual_assets": core_policy["project_specific_modules"]["accepted_manual_assets_retained_in_repo"],
            "accepted_processed_artifact_groups": accepted_processed_groups,
        },
        "future_split_candidates": core_policy["future_project_repo_candidates"],
        "project_tuned_runtime_modules": {
            "paths": core_policy["project_specific_modules"]["project_tuned_runtime_modules"],
            "remaining_known_couplings": retrieval_couplings,
        },
        "processed_policy_alignment": {
            "allowed_processed_inputs_for_clean_rebuild": processed_policy["authoritative_input_rules"][
                "allowed_processed_inputs_for_clean_rebuild"
            ],
            "accepted_project_group": "accepted_project_operational_artifact",
            "notes": [
                "Accepted project processed artifacts remain authoritative inputs for clean rebuild support.",
                "Runtime-contract outputs are still rebuilt in place and are not moved into the project grouping area.",
            ],
        },
        "notes": [
            "This task intentionally avoids moving runtime-contract artifacts, live source manuals, or golden sets.",
            "The grouping area is designed to reduce ambiguity now and lower risk when the case-specific repository is created later.",
        ],
    }


def update_core_policy(core_policy: dict) -> dict:
    core_policy["policy_version"] = 2
    core_policy["project_specific_grouping_area"] = {
        "path": "projects/broaching-cnc-8070/",
        "manifest": "projects/broaching-cnc-8070/project_scope_manifest.json",
        "boundary_registry": "data/processed/t27_project_specific_boundary_registry.json",
        "status": "canonical_grouping_area_for_retained_project_scope",
        "notes": [
            "The grouping area makes the retained broaching/CNC reference scope visible without moving the live project paths yet.",
            "Current project paths remain in place for compatibility and rebuildability until the dedicated case-specific repository exists.",
        ],
    }
    return core_policy


def update_processed_policy(processed_policy: dict) -> dict:
    processed_policy["policy_version"] = 2
    processed_policy["project_specific_visibility"] = {
        "project_grouping_area": "projects/broaching-cnc-8070/",
        "manifest": "projects/broaching-cnc-8070/project_scope_manifest.json",
        "boundary_registry": "data/processed/t27_project_specific_boundary_registry.json",
        "notes": [
            "Accepted project operational artifacts remain in data/processed but are now grouped contractually under the retained project boundary.",
            "This visibility layer is contractual and documentary; it does not change the runtime rebuild contract.",
        ],
    }
    return processed_policy


def update_processed_registry(processed_registry: dict) -> dict:
    processed_registry["registry_version"] = 2
    for entry in processed_registry["registry"]:
        if entry.get("policy_group") == "accepted_project_operational_artifact":
            entry["project_grouping_area"] = "projects/broaching-cnc-8070/"
            entry["project_scope_manifest"] = "projects/broaching-cnc-8070/project_scope_manifest.json"
    return processed_registry


def update_structure_report(structure_report: dict) -> dict:
    structure_report["task_009_project_specific_actions"] = {
        "applied": True,
        "project_grouping_area": "projects/broaching-cnc-8070/",
        "project_scope_manifest": "projects/broaching-cnc-8070/project_scope_manifest.json",
        "boundary_registry": "data/processed/t27_project_specific_boundary_registry.json",
        "physically_moved_paths": [],
        "retained_in_place_for_compatibility": [
            "cache/terms_cache.json",
            "data/raw/",
            "data/golden_set/",
            "data/processed/a218_*",
            "data/processed/quick_ref_*",
            "data/processed/installation_manual_* and data/processed/8070_installation_*",
            "data/processed/man_8070_err_*",
        ],
        "notes": [
            "Task 009 used a canonical grouping area and registries instead of moving live paths.",
            "Project-tuned retrieval modules remain in place and were made more explicit as retained project coupling.",
        ],
    }
    return structure_report


def main() -> None:
    core_policy = load_json(CORE_POLICY_PATH)
    processed_policy = load_json(PROCESSED_POLICY_PATH)
    processed_registry = load_json(PROCESSED_REGISTRY_PATH)
    structure_report = load_json(STRUCTURE_REPORT_PATH)

    core_policy = update_core_policy(core_policy)
    processed_policy = update_processed_policy(processed_policy)
    processed_registry = update_processed_registry(processed_registry)
    structure_report = update_structure_report(structure_report)

    project_manifest = build_project_manifest(core_policy, processed_registry)
    boundary_registry = build_boundary_registry(
        core_policy=core_policy,
        processed_policy=processed_policy,
        processed_registry=processed_registry,
        structure_report=structure_report,
    )

    dump_json(CORE_POLICY_PATH, core_policy)
    dump_json(PROCESSED_POLICY_PATH, processed_policy)
    dump_json(PROCESSED_REGISTRY_PATH, processed_registry)
    dump_json(STRUCTURE_REPORT_PATH, structure_report)
    dump_json(PROJECT_MANIFEST_PATH, project_manifest)
    dump_json(BOUNDARY_REGISTRY_PATH, boundary_registry)


if __name__ == "__main__":
    main()
