from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = REPO_ROOT / "data" / "processed" / "t27_repo_reusability_inventory.json"
POLICY_PATH = REPO_ROOT / "data" / "processed" / "t27_core_vs_project_policy.json"
POLICY_OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "t27_processed_artifact_policy.json"
REGISTRY_OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "t27_processed_artifact_registry.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["path"]): item for item in items}


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def is_processed_artifact(path: str) -> bool:
    normalized = normalize_path(path)
    return normalized.startswith("data/processed/")


def infer_policy_group(item: dict[str, Any]) -> str:
    path = str(item["path"])
    category = str(item["category"])

    if not is_processed_artifact(path):
        raise ValueError(f"Non-processed artifact passed to processed registry: {path}")

    if category == "runtime_contract":
        return "runtime_contract"
    if category == "accepted_project_artifact":
        return "accepted_project_operational_artifact"
    if category in {"candidate_for_archive", "historical_campaign_tooling"}:
        return "historical_campaign_traceability"
    if category == "debug_or_diagnostic":
        return "debug_and_diagnostics"

    raise ValueError(f"Unsupported processed artifact category for {path}: {category}")


def authoritativeness(group: str, path: str) -> dict[str, Any]:
    if group == "runtime_contract":
        return {
            "authoritative_for_runtime_consumption": True,
            "authoritative_for_clean_rebuild_input": False,
            "authoritative_for_validation": True,
            "notes": (
                "Live runtime artifacts define the active runtime state once produced, but a clean rebuild "
                "should regenerate them from source/manual-level inputs rather than consume them as primary "
                "source truth."
            ),
        }
    if group == "accepted_project_operational_artifact":
        return {
            "authoritative_for_runtime_consumption": False,
            "authoritative_for_clean_rebuild_input": True,
            "authoritative_for_validation": True,
            "notes": (
                "Accepted manual-level operational artifacts may be consumed as project onboarding state or "
                "manual-level rebuild continuity, but they are not the single global runtime contract."
            ),
        }
    if group == "historical_campaign_traceability":
        return {
            "authoritative_for_runtime_consumption": False,
            "authoritative_for_clean_rebuild_input": False,
            "authoritative_for_validation": False,
            "notes": (
                "Historical campaign outputs remain traceable but must never define the runtime contract or "
                "clean rebuild inputs."
            ),
        }
    if group == "debug_and_diagnostics":
        return {
            "authoritative_for_runtime_consumption": False,
            "authoritative_for_clean_rebuild_input": False,
            "authoritative_for_validation": False,
            "notes": (
                "Diagnostic outputs are explicitly non-contractual and may be refreshed or overwritten during "
                "investigation without changing the runtime contract."
            ),
        }
    raise ValueError(f"Unsupported policy group: {group}")


def lifecycle_policy(group: str) -> dict[str, Any]:
    if group == "runtime_contract":
        return {
            "rebuild_policy": "rebuild_from_stable_runtime_path",
            "preservation_policy": "overwrite_with_fresh_runtime_outputs",
            "candidate_for_future_archive": False,
            "non_contractual": False,
        }
    if group == "accepted_project_operational_artifact":
        return {
            "rebuild_policy": "rebuild_or_refresh_from_accepted_project_scope",
            "preservation_policy": "preserve_as_project_operational_state",
            "candidate_for_future_archive": False,
            "non_contractual": False,
        }
    if group == "historical_campaign_traceability":
        return {
            "rebuild_policy": "preserve_only_do_not_consume_as_runtime_input",
            "preservation_policy": "preserve_for_traceability",
            "candidate_for_future_archive": True,
            "non_contractual": True,
        }
    if group == "debug_and_diagnostics":
        return {
            "rebuild_policy": "refresh_or_overwrite_when_debugging",
            "preservation_policy": "retain_temporarily_or_archive_separately",
            "candidate_for_future_archive": True,
            "non_contractual": True,
        }
    raise ValueError(f"Unsupported policy group: {group}")


def registry_record(item: dict[str, Any]) -> dict[str, Any]:
    path = str(item["path"])
    group = infer_policy_group(item)
    authority = authoritativeness(group, path)
    lifecycle = lifecycle_policy(group)
    return {
        "path": path,
        "type": item["type"],
        "inventory_category": item["category"],
        "policy_group": group,
        "runtime_critical": item["runtime_critical"],
        "project_specific": item["project_specific"],
        "recommended_action": item["recommended_action"],
        **authority,
        **lifecycle,
        "notes": item["notes"],
    }


def count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record[key])
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def main() -> None:
    inventory = load_json(INVENTORY_PATH)
    policy = load_json(POLICY_PATH)
    items = inventory["items"]
    processed_items = [item for item in items if is_processed_artifact(str(item["path"]))]
    registry = sorted(
        [registry_record(item) for item in processed_items],
        key=lambda record: (record["policy_group"], record["path"]),
    )

    policy_payload = {
        "task": "T27A-004",
        "policy_version": 1,
        "generated_from": "misc/coding-team/repo-reusability-core-split/generate_processed_artifact_policy.py",
        "source_inventory": str(INVENTORY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "source_policy": str(POLICY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "policy_goal": (
            "Treat data/processed as a governed artifact space with explicit runtime, project-operational, "
            "historical, and diagnostic semantics instead of as a flat namespace."
        ),
        "historical_tooling_declassified_from_operational_path": bool(
            policy["historical_tooling_declassified_from_operational_path"]
        ),
        "processed_policy_groups": {
            "runtime_contract": {
                "description": (
                    "Live runtime artifacts that define the active runtime state after a rebuild, publication, "
                    "or validation cycle."
                ),
                "allowed_to_define_runtime_contract": True,
                "allowed_as_clean_rebuild_authoritative_input": False,
                "default_lifecycle": lifecycle_policy("runtime_contract"),
            },
            "accepted_project_operational_artifact": {
                "description": (
                    "Accepted manual-level outputs retained for project continuity, onboarding traceability, "
                    "and accepted-scope rebuild support."
                ),
                "allowed_to_define_runtime_contract": False,
                "allowed_as_clean_rebuild_authoritative_input": True,
                "default_lifecycle": lifecycle_policy("accepted_project_operational_artifact"),
            },
            "historical_campaign_traceability": {
                "description": (
                    "Historical outputs from completed campaigns and cleanup work that remain useful for "
                    "traceability but are non-contractual."
                ),
                "allowed_to_define_runtime_contract": False,
                "allowed_as_clean_rebuild_authoritative_input": False,
                "default_lifecycle": lifecycle_policy("historical_campaign_traceability"),
            },
            "debug_and_diagnostics": {
                "description": (
                    "Transient audit and debug outputs that may be overwritten during investigation and must "
                    "never be consumed as authoritative runtime state."
                ),
                "allowed_to_define_runtime_contract": False,
                "allowed_as_clean_rebuild_authoritative_input": False,
                "default_lifecycle": lifecycle_policy("debug_and_diagnostics"),
            },
        },
        "authoritative_input_rules": {
            "allowed_processed_inputs_for_clean_rebuild": [
                "accepted_project_operational_artifact"
            ],
            "disallowed_processed_inputs_for_clean_rebuild": [
                "runtime_contract",
                "historical_campaign_traceability",
                "debug_and_diagnostics",
            ],
            "notes": [
                "A clean rebuild should prefer source manuals, accepted manifests, and explicit project config.",
                "Runtime-contract outputs may be consumed after they are rebuilt, but they are not the authoritative source for rebuilding themselves.",
                "Historical and diagnostic artifacts remain visible for traceability but are explicitly excluded from runtime input contracts.",
            ],
        },
        "processed_namespace_policy": {
            "rebuild_category_a_from_scratch": True,
            "rebuild_category_b_for_accepted_project_scope": True,
            "preserve_category_c_for_traceability": True,
            "allow_category_d_to_be_overwritten": True,
            "do_not_physically_move_processed_contents_in_t27a": True,
        },
        "registry_summary": {
            "processed_item_count": len(registry),
            "counts_by_policy_group": count_by(registry, "policy_group"),
            "counts_by_inventory_category": count_by(registry, "inventory_category"),
            "non_contractual_count": sum(1 for record in registry if bool(record["non_contractual"])),
            "candidate_for_future_archive_count": sum(
                1 for record in registry if bool(record["candidate_for_future_archive"])
            ),
        },
        "notes": [
            "This policy is contractual and documentary in T27A; it does not move or delete processed artifacts.",
            "The registry is intended to support later archival or relocation work without changing the runtime contract in T27A.",
        ],
    }

    registry_payload = {
        "task": "T27A-004",
        "registry_version": 1,
        "generated_from": "misc/coding-team/repo-reusability-core-split/generate_processed_artifact_policy.py",
        "source_inventory": str(INVENTORY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "source_policy": str(POLICY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "item_count": len(registry),
        "counts_by_policy_group": count_by(registry, "policy_group"),
        "registry": registry,
    }

    POLICY_OUTPUT_PATH.write_text(json.dumps(policy_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REGISTRY_OUTPUT_PATH.write_text(json.dumps(registry_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
