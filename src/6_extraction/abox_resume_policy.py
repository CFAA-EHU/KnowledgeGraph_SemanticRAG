import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import json

from artifact_contracts import (
    ABOX_CONTENT_ERROR_CAUSES,
    ABOX_RETRYABLE_ERROR_CAUSES,
    abox_reuse_signature_dict,
    build_abox_reuse_signature,
    is_reusable_abox_output,
)

VALID_MANIFEST_STATUSES = {"ok", "error", "missing", "stale"}
VALID_RESUME_MODES = {"resume-compatible", "force-stale", "force-all"}
VALID_ERROR_CAUSES = ABOX_RETRYABLE_ERROR_CAUSES.union(ABOX_CONTENT_ERROR_CAUSES)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_manifest(manifest_path: Path) -> dict[str, dict]:
    if not manifest_path.exists():
        return {}

    with open(manifest_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, dict) and isinstance(payload.get("chunks"), dict):
        chunks = payload["chunks"]
    elif isinstance(payload, dict):
        chunks = payload
    else:
        raise ValueError("El manifiesto A-Box debe ser un objeto JSON legible.")

    normalized: dict[str, dict] = {}
    for chunk_id, entry in chunks.items():
        if isinstance(entry, dict):
            normalized[str(chunk_id)] = entry
    return normalized


def save_manifest(manifest_path: Path, manifest_entries: dict[str, dict]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "chunks": dict(sorted(manifest_entries.items(), key=lambda item: int(item[0]))),
        "updated_at": utc_now_iso(),
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def build_manifest_entry(
    chunk_data: dict,
    *,
    output_path: Path,
    status: str,
    prompt_version: str,
    model_name: str,
    extraction_mode: str,
    tbox_hash: str,
    error_cause: str | None = None,
    error_message: str | None = None,
    semantic_report: dict | None = None,
) -> dict:
    if status not in VALID_MANIFEST_STATUSES:
        raise ValueError(f"Estado de manifiesto no soportado: {status}")
    if error_cause and error_cause not in VALID_ERROR_CAUSES:
        raise ValueError(f"Causa de error no soportada: {error_cause}")

    signature = build_abox_reuse_signature(
        chunk_data["texto_fuente"],
        chunk_data=chunk_data,
        prompt_version=prompt_version,
        model_name=model_name,
        extraction_mode=extraction_mode,
        tbox_hash=tbox_hash,
    )

    entry = {
        "chunk_id": chunk_data["chunk_id"],
        "output_path": str(output_path),
        "status": status,
        **abox_reuse_signature_dict(signature),
        "last_updated": utc_now_iso(),
    }
    if error_cause:
        entry["error_cause"] = error_cause
    if error_message:
        entry["error_message"] = error_message
    if semantic_report:
        entry["semantic_report"] = semantic_report
    return entry


def determine_chunk_action(
    chunk_data: dict,
    *,
    output_path: Path,
    manifest_entry: dict | None,
    mode: str,
    prompt_version: str,
    model_name: str,
    extraction_mode: str,
    compatible_model_names: tuple[str, ...] | None = None,
    tbox_hash: str,
) -> tuple[str, str]:
    if mode not in VALID_RESUME_MODES:
        raise ValueError(f"Modo de reanudacion no soportado: {mode}")

    output_exists = output_path.exists()
    signature_fields = None
    if manifest_entry:
        signature_fields = {
            key: manifest_entry.get(key)
            for key in ("source_text_hash", "chunk_hash", "tbox_hash", "prompt_version", "model_name", "extraction_mode")
        }

    compatible = output_exists and is_reusable_abox_output(
        signature_fields,
        source_text=chunk_data["texto_fuente"],
        chunk_data=chunk_data,
        prompt_version=prompt_version,
        model_name=model_name,
        extraction_mode=extraction_mode,
        compatible_model_names=compatible_model_names,
        tbox_hash=tbox_hash,
    ) and manifest_entry is not None and manifest_entry.get("status") == "ok"

    if mode == "force-all":
        return "regenerate", "stale"
    if compatible:
        return "reuse", "ok"
    if not output_exists:
        return "regenerate", "missing"
    if not manifest_entry:
        return "regenerate", "stale"
    if manifest_entry.get("status") == "error":
        return "regenerate", "error"
    return "regenerate", "stale"
