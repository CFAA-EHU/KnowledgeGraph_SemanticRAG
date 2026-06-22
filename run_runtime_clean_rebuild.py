from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
EXTRACTION_DIR = REPO_ROOT / "src" / "6_extraction"
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

from artifact_contracts import (
    ABOX_CHUNKS_DIR,
    CANONICAL_ABOX_PATH,
    CROSS_EVAL_REPORT_PATH,
    DENSITY_REPORT_PATH,
    ENRICHED_ABOX_PATH,
    GENERALIZATION_EVAL_REPORT_PATH,
    GRAPHDB_PUBLICATION_REPORT_PATH,
    MAN_8070_ERR_DECISION_REPORT_PATH,
    MAN_8070_ERR_EVAL_REPORT_PATH,
    MULTIHOP_EVAL_REPORT_PATH,
    MULTILINGUAL_LEXICON_PATH,
    OPERATIONAL_ABOX_INPUT_PATH,
    OPERATIONAL_ABOX_MANIFEST_PATH,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
    PROCESSED_DATA_DIR,
    QA_CANONICAL_PATH,
    QA_CROSS_PATH,
    QA_MULTIHOP_PATH,
    QA_8070_QUICK_REF_BILINGUAL_V2_PATH,
    QUICK_REF_V2_EVAL_REPORT_PATH,
    RAW_DATA_DIR,
    RAW_MERGED_ABOX_PATH,
    hash_file_content,
    is_reusable_abox_output,
    resolve_ollama_model_chain,
)
from abox_resume_policy import load_manifest, save_manifest


@dataclass(frozen=True)
class ManualRebuildSpec:
    manual_id: str
    source_chunks: Path
    artifact_prefix: str
    eval_dataset_path: Path | None = None
    eval_report_path: Path | None = None
    decision_report_path: Path | None = None

    @property
    def density_report_path(self) -> Path:
        return PROCESSED_DATA_DIR / f"{self.artifact_prefix}_density_report.json"

    @property
    def language_detection_report_path(self) -> Path:
        return PROCESSED_DATA_DIR / f"{self.artifact_prefix}_language_detection_report.json"

    @property
    def abox_input_path(self) -> Path:
        return PROCESSED_DATA_DIR / f"{self.artifact_prefix}_abox_input.json"

    @property
    def manifest_path(self) -> Path:
        return PROCESSED_DATA_DIR / f"{self.artifact_prefix}_abox_generation_manifest.json"

    @property
    def chunks_dir(self) -> Path:
        return PROCESSED_DATA_DIR / f"{self.artifact_prefix}_abox_graphs"

    @property
    def debug_dir(self) -> Path:
        return PROCESSED_DATA_DIR / f"{self.artifact_prefix}_abox_debug"

    @property
    def merged_path(self) -> Path:
        return PROCESSED_DATA_DIR / f"{self.artifact_prefix}_merged.ttl"


ACCEPTED_MANUALS: tuple[ManualRebuildSpec, ...] = (
    ManualRebuildSpec(
        manual_id="a218",
        source_chunks=RAW_DATA_DIR / "chunks_manual_instrucciones_a218.txt",
        artifact_prefix="a218",
    ),
    ManualRebuildSpec(
        manual_id="variables_cnc_8070",
        source_chunks=RAW_DATA_DIR / "chunks_manual_variables_cnc_8070.txt",
        artifact_prefix="variables_cnc",
    ),
    ManualRebuildSpec(
        manual_id="8070_installation",
        source_chunks=RAW_DATA_DIR / "chunks_8070_installation_manual.txt",
        artifact_prefix="installation_manual",
        eval_dataset_path=REPO_ROOT / "data" / "golden_set" / "QA_chunks_8070_installation_manual.json",
        eval_report_path=PROCESSED_DATA_DIR / "8070_installation_eval_report.json",
        decision_report_path=PROCESSED_DATA_DIR / "8070_installation_decision_report.json",
    ),
    ManualRebuildSpec(
        manual_id="8070_quick_ref",
        source_chunks=RAW_DATA_DIR / "chunks_8070_quick_ref.txt",
        artifact_prefix="quick_ref",
    ),
    ManualRebuildSpec(
        manual_id="man_8070_err",
        source_chunks=RAW_DATA_DIR / "chunks_man_8070_err.txt",
        artifact_prefix="man_8070_err",
        eval_dataset_path=REPO_ROOT / "data" / "golden_set" / "QA_chunks_man_8070_err.json",
        eval_report_path=MAN_8070_ERR_EVAL_REPORT_PATH,
        decision_report_path=MAN_8070_ERR_DECISION_REPORT_PATH,
    ),
)

REBUILD_REPORT_PATH = PROCESSED_DATA_DIR / "runtime_clean_rebuild_report.json"
REBUILD_PREFLIGHT_PATH = PROCESSED_DATA_DIR / "runtime_clean_rebuild_preflight.json"
ABOX_PROMPT_VERSION = "semantic-guardrails-v4-identity-rules"
ABOX_EXTRACTION_MODE = "abox_from_text_chunk"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild limpio multi-manual del runtime operativo.")
    parser.add_argument(
        "--mode",
        choices=["resume-compatible", "force-stale", "force-all"],
        default="resume-compatible",
        help="Modo del extractor A-Box.",
    )
    parser.add_argument(
        "--retry-profile",
        choices=["standard", "rate-limit-drain", "micro-batch-recovery", "local-high-throughput"],
        default="local-high-throughput",
        help="Perfil de reintentos del extractor A-Box.",
    )
    parser.add_argument(
        "--skip-publish",
        action="store_true",
        help="No publicar el runtime a GraphDB al finalizar.",
    )
    parser.add_argument(
        "--allow-partial-extraction",
        action="store_true",
        help="Continuar el rebuild aunque el extractor A-Box reporte errores parciales (chunks fallidos < 100%).",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_path_exists(path: Path, message: str) -> None:
    if not path.exists():
        raise SystemExit(message)


def snapshot_existing_runtime() -> None:
    snapshot_paths = [
        DENSITY_REPORT_PATH,
        OPERATIONAL_ABOX_INPUT_PATH,
        OPERATIONAL_ABOX_MANIFEST_PATH,
        RAW_MERGED_ABOX_PATH,
        CANONICAL_ABOX_PATH,
        ENRICHED_ABOX_PATH,
        OPERATIONAL_ABOX_PATH,
        MULTILINGUAL_LEXICON_PATH,
        GRAPHDB_PUBLICATION_REPORT_PATH,
    ]
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "paths": {
            str(path): {
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
                "last_modified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(path.stat().st_mtime))
                if path.exists()
                else None,
            }
            for path in snapshot_paths
        },
    }
    write_json(REBUILD_PREFLIGHT_PATH, payload)


def run_stage(args: list[str], *, label: str, allow_partial: bool = False) -> dict:
    command = [sys.executable, *args]
    print(f"\n[clean-rebuild] Ejecutando: {label}")
    started_at = time.time()
    result = subprocess.run(command, cwd=REPO_ROOT)
    duration_seconds = round(time.time() - started_at, 3)
    if result.returncode != 0:
        if allow_partial:
            print(f"[clean-rebuild] Advertencia: {label} finalizo con codigo {result.returncode} (allow-partial-extraction activo, continuando)")
        else:
            raise SystemExit(f"Fallo la fase {label} con codigo {result.returncode}")
    return {
        "label": label,
        "command": command,
        "duration_seconds": duration_seconds,
        "returncode": result.returncode,
    }


def refresh_terms_cache(stage_records: list[dict]) -> None:
    args = ["src/1_ingestion/termLoader.py", "--refresh"]
    for manual in ACCEPTED_MANUALS:
        args.extend(["--input", str(manual.source_chunks)])
    stage_records.append(run_stage(args, label="termLoader_refresh_multi_manual"))


def rebuild_density_and_inputs(stage_records: list[dict]) -> None:
    for manual in ACCEPTED_MANUALS:
        stage_records.append(
            run_stage(
                [
                    "src/1_ingestion/density_analyzer.py",
                    "--input",
                    str(manual.source_chunks),
                    "--manual-id",
                    manual.manual_id,
                    "--output",
                    str(manual.density_report_path),
                    "--language-report-path",
                    str(manual.language_detection_report_path),
                ],
                label=f"{manual.artifact_prefix}_density_analyzer",
            )
        )
        stage_records.append(
            run_stage(
                [
                    "src/6_extraction/abox_input_builder.py",
                    "--density-report",
                    str(manual.density_report_path),
                    "--output",
                    str(manual.abox_input_path),
                    "--manual-id",
                    manual.manual_id,
                ],
                label=f"{manual.artifact_prefix}_abox_input_builder",
            )
        )


def load_abox_input_payload(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"A-Box input invalido: {path}")
    return payload


def manual_outputs_match_current_input(manual: ManualRebuildSpec) -> bool:
    if not manual.manifest_path.exists() or not manual.chunks_dir.exists():
        return False

    abox_input = load_abox_input_payload(manual.abox_input_path)
    manifest_entries = load_manifest(manual.manifest_path)
    model_chain = resolve_ollama_model_chain()
    primary_model = model_chain[0]
    tbox_hash = hash_file_content(OPERATIONAL_TBOX_PATH)

    for chunk in abox_input:
        chunk_id = int(chunk["chunk_id"])
        output_path = manual.chunks_dir / f"chunk_{chunk_id:03d}_abox.ttl"
        if not output_path.exists():
            return False
        manifest_entry = manifest_entries.get(str(chunk_id))
        if not isinstance(manifest_entry, dict) or manifest_entry.get("status") != "ok":
            return False
        signature_fields = {
            key: manifest_entry.get(key)
            for key in ("source_text_hash", "chunk_hash", "tbox_hash", "prompt_version", "model_name", "extraction_mode")
        }
        if not is_reusable_abox_output(
            signature_fields,
            source_text=chunk["texto_fuente"],
            chunk_data=chunk,
            prompt_version=ABOX_PROMPT_VERSION,
            model_name=primary_model,
            extraction_mode=ABOX_EXTRACTION_MODE,
            compatible_model_names=model_chain,
            tbox_hash=tbox_hash,
        ):
            return False
    return True


def extract_and_merge_manuals(stage_records: list[dict], *, mode: str, retry_profile: str, allow_partial: bool = False) -> None:
    for manual in ACCEPTED_MANUALS:
        if manual_outputs_match_current_input(manual):
            stage_records.append(
                {
                    "label": f"{manual.artifact_prefix}_abox_extractor",
                    "command": [],
                    "duration_seconds": 0.0,
                    "returncode": 0,
                    "skipped": True,
                    "reason": "compatible_outputs_reused_without_reextract",
                }
            )
        else:
            stage_records.append(
                run_stage(
                    [
                        "src/6_extraction/abox_extractor.py",
                        "--mode",
                        mode,
                        "--retry-profile",
                        retry_profile,
                        "--abox-input",
                        str(manual.abox_input_path),
                        "--manifest-path",
                        str(manual.manifest_path),
                        "--output-dir",
                        str(manual.chunks_dir),
                        "--debug-dir",
                        str(manual.debug_dir),
                    ],
                    label=f"{manual.artifact_prefix}_abox_extractor",
                    allow_partial=allow_partial,
                )
            )
        stage_records.append(
            run_stage(
                [
                    "src/6_extraction/abox_merger.py",
                    "--input-dir",
                    str(manual.chunks_dir),
                    "--output",
                    str(manual.merged_path),
                ],
                label=f"{manual.artifact_prefix}_abox_merger",
            )
        )


def rebuild_global_density_report() -> dict[str, dict[int, int]]:
    combined_chunks: list[dict] = []
    mapping: dict[str, dict[int, int]] = {}
    next_global_chunk_id = 1

    for manual in ACCEPTED_MANUALS:
        chunks = json.loads(manual.density_report_path.read_text(encoding="utf-8"))
        if not isinstance(chunks, list):
            raise SystemExit(f"Density report invalido: {manual.density_report_path}")
        manual_mapping: dict[int, int] = {}
        for chunk in chunks:
            local_chunk_id = int(chunk["chunk_id"])
            chunk_copy = dict(chunk)
            chunk_copy["source_manual_chunk_id"] = local_chunk_id
            chunk_copy["chunk_id"] = next_global_chunk_id
            chunk_copy["manual_id"] = chunk.get("manual_id") or manual.manual_id
            combined_chunks.append(chunk_copy)
            manual_mapping[local_chunk_id] = next_global_chunk_id
            next_global_chunk_id += 1
        mapping[manual.manual_id] = manual_mapping

    DENSITY_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DENSITY_REPORT_PATH.write_text(json.dumps(combined_chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    return mapping


def rebuild_global_abox_input(stage_records: list[dict]) -> None:
    stage_records.append(
        run_stage(
            [
                "src/6_extraction/abox_input_builder.py",
                "--density-report",
                str(DENSITY_REPORT_PATH),
                "--output",
                str(OPERATIONAL_ABOX_INPUT_PATH),
            ],
            label="operational_abox_input_builder",
        )
    )


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def synthesize_global_chunk_contract(mapping: dict[str, dict[int, int]]) -> None:
    reset_directory(ABOX_CHUNKS_DIR)
    global_manifest_entries: dict[str, dict] = {}

    for manual in ACCEPTED_MANUALS:
        manual_manifest = load_manifest(manual.manifest_path)
        manual_mapping = mapping[manual.manual_id]
        for local_chunk_id, global_chunk_id in sorted(manual_mapping.items()):
            source_ttl = manual.chunks_dir / f"chunk_{local_chunk_id:03d}_abox.ttl"
            ensure_path_exists(source_ttl, f"Falta el TTL reconstruido para {manual.manual_id} chunk {local_chunk_id}: {source_ttl}")
            target_ttl = ABOX_CHUNKS_DIR / f"chunk_{global_chunk_id:03d}_abox.ttl"
            shutil.copy2(source_ttl, target_ttl)

            manifest_entry = manual_manifest.get(str(local_chunk_id))
            if not isinstance(manifest_entry, dict):
                raise SystemExit(f"Falta el manifest entry para {manual.manual_id} chunk {local_chunk_id}")
            merged_entry = dict(manifest_entry)
            merged_entry["chunk_id"] = global_chunk_id
            merged_entry["output_path"] = str(target_ttl)
            global_manifest_entries[str(global_chunk_id)] = merged_entry

    save_manifest(OPERATIONAL_ABOX_MANIFEST_PATH, global_manifest_entries)


def rebuild_runtime_graphs(stage_records: list[dict]) -> None:
    stage_records.append(
        run_stage(
            [
                "src/6_extraction/abox_merger.py",
                "--input-dir",
                str(ABOX_CHUNKS_DIR),
                "--output",
                str(RAW_MERGED_ABOX_PATH),
            ],
            label="operational_abox_merger",
        )
    )
    stage_records.append(run_stage(["src/6_extraction/abox_canonicalizer.py"], label="abox_canonicalizer"))
    stage_records.append(run_stage(["src/6_extraction/abox_graph_enricher.py"], label="abox_graph_enricher"))
    stage_records.append(run_stage(["src/6_extraction/abox_link_completer.py"], label="abox_link_completer"))
    stage_records.append(
        run_stage(
            [
                "src/8_retrieval/multilingual_lexicon_builder.py",
                "--abox-file",
                str(OPERATIONAL_ABOX_PATH),
                "--output",
                str(MULTILINGUAL_LEXICON_PATH),
            ],
            label="multilingual_lexicon_builder",
        )
    )


def run_validation(stage_records: list[dict]) -> None:
    stage_records.append(
        run_stage(
            [
                "-m",
                "py_compile",
                "artifact_contracts.py",
                "run_operational_pipeline.py",
                "run_runtime_clean_rebuild.py",
                "src/6_extraction/abox_extractor.py",
                "src/6_extraction/abox_canonicalizer.py",
                "src/8_retrieval/qa_evaluator.py",
            ],
            label="py_compile_runtime_clean_rebuild",
        )
    )

    qa_runs = [
        ("qa_evaluator_canonical", [str(QA_CANONICAL_PATH), str(GENERALIZATION_EVAL_REPORT_PATH)]),
        ("qa_evaluator_multihop", [str(QA_MULTIHOP_PATH), str(MULTIHOP_EVAL_REPORT_PATH)]),
        ("qa_evaluator_quick_ref_v2", [str(QA_8070_QUICK_REF_BILINGUAL_V2_PATH), str(QUICK_REF_V2_EVAL_REPORT_PATH)]),
        ("qa_evaluator_cross", [str(QA_CROSS_PATH), str(CROSS_EVAL_REPORT_PATH)]),
    ]

    for label, (dataset_path, report_path) in qa_runs:
        stage_records.append(
            run_stage(
                [
                    "src/8_retrieval/qa_evaluator.py",
                    "--qa-file",
                    dataset_path,
                    "--report-path",
                    report_path,
                ],
                label=label,
            )
        )

    for manual in ACCEPTED_MANUALS:
        if manual.eval_dataset_path and manual.eval_report_path:
            stage_records.append(
                run_stage(
                    [
                        "src/8_retrieval/qa_evaluator.py",
                        "--qa-file",
                        str(manual.eval_dataset_path),
                        "--report-path",
                        str(manual.eval_report_path),
                    ],
                    label=f"{manual.artifact_prefix}_qa_evaluator",
                )
            )


def publish_and_check_graphdb(stage_records: list[dict], *, skip_publish: bool) -> None:
    if not skip_publish:
        stage_records.append(run_stage(["src/7_database/publish_to_graphdb.py"], label="publish_to_graphdb"))
    stage_records.append(run_stage(["src/7_database/graphdb_healthcheck.py"], label="graphdb_healthcheck"))


def gather_summary(mapping: dict[str, dict[int, int]], stage_records: list[dict], *, mode: str, retry_profile: str, skip_publish: bool) -> dict:
    manuals_payload = []
    for manual in ACCEPTED_MANUALS:
        manuals_payload.append(
            {
                "manual_id": manual.manual_id,
                "source_chunks": str(manual.source_chunks),
                "artifact_prefix": manual.artifact_prefix,
                "eval_dataset_path": str(manual.eval_dataset_path) if manual.eval_dataset_path else None,
                "eval_report_path": str(manual.eval_report_path) if manual.eval_report_path else None,
                "decision_report_path": str(manual.decision_report_path) if manual.decision_report_path else None,
            }
        )
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "accepted_manuals": manuals_payload,
        "mode": mode,
        "retry_profile": retry_profile,
        "skip_publish": skip_publish,
        "global_chunk_count": sum(len(manual_mapping) for manual_mapping in mapping.values()),
        "manual_chunk_counts": {manual_id: len(manual_mapping) for manual_id, manual_mapping in mapping.items()},
        "operational_paths": {
            "density_report": str(DENSITY_REPORT_PATH),
            "abox_input": str(OPERATIONAL_ABOX_INPUT_PATH),
            "abox_manifest": str(OPERATIONAL_ABOX_MANIFEST_PATH),
            "abox_chunks_dir": str(ABOX_CHUNKS_DIR),
            "abox_merged": str(RAW_MERGED_ABOX_PATH),
            "abox_canonical": str(CANONICAL_ABOX_PATH),
            "abox_enriched": str(ENRICHED_ABOX_PATH),
            "abox_linked": str(OPERATIONAL_ABOX_PATH),
            "multilingual_lexicon": str(MULTILINGUAL_LEXICON_PATH),
            "graphdb_publication_report": str(GRAPHDB_PUBLICATION_REPORT_PATH),
        },
        "stage_records": stage_records,
    }


def main() -> None:
    args = parse_args()
    stage_records: list[dict] = []

    for manual in ACCEPTED_MANUALS:
        ensure_path_exists(manual.source_chunks, f"Falta el manual aceptado: {manual.source_chunks}")

    snapshot_existing_runtime()
    refresh_terms_cache(stage_records)
    rebuild_density_and_inputs(stage_records)
    extract_and_merge_manuals(stage_records, mode=args.mode, retry_profile=args.retry_profile, allow_partial=args.allow_partial_extraction)
    mapping = rebuild_global_density_report()
    rebuild_global_abox_input(stage_records)
    synthesize_global_chunk_contract(mapping)
    rebuild_runtime_graphs(stage_records)
    run_validation(stage_records)
    publish_and_check_graphdb(stage_records, skip_publish=args.skip_publish)

    summary = gather_summary(mapping, stage_records, mode=args.mode, retry_profile=args.retry_profile, skip_publish=args.skip_publish)
    write_json(REBUILD_REPORT_PATH, summary)

    print("\n[clean-rebuild] Rebuild limpio completado.")
    print(f"- Manuales aceptados: {len(ACCEPTED_MANUALS)}")
    print(f"- Chunks globales: {summary['global_chunk_count']}")
    print(f"- A-Box linked: {OPERATIONAL_ABOX_PATH}")
    print(f"- Reporte: {REBUILD_REPORT_PATH}")


if __name__ == "__main__":
    main()
