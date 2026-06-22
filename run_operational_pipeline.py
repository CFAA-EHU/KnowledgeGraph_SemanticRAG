from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from artifact_contracts import (
    CANONICAL_ABOX_PATH,
    ENRICHED_ABOX_PATH,
    GENERALIZATION_EVAL_REPORT_PATH,
    MULTIHOP_EVAL_REPORT_PATH,
    MULTILINGUAL_LEXICON_PATH,
    OPERATIONAL_ABOX_INPUT_PATH,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_BUILD_PIPELINE,
    OPERATIONAL_TBOX_PATH,
    QA_CANONICAL_PATH,
    QA_MULTIHOP_PATH,
    RAW_MERGED_ABOX_PATH,
    SCHEMA_CONDENSED_PATH,
    build_onboarding_profile,
)

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_MODE = "resume-compatible"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Entrypoint del build operativo canonico, enriched, linked y bilingue.")
    parser.add_argument(
        "--mode",
        choices=["resume-compatible", "force-stale", "force-all"],
        default=DEFAULT_MODE,
        help="Modo de ejecucion para la extraccion A-Box.",
    )
    parser.add_argument(
        "--source-chunks",
        type=Path,
        default=None,
        help="Ruta opcional a un manual/chunks para ejecutar onboarding piloto con artefactos propios.",
    )
    parser.add_argument(
        "--manual-id",
        default="",
        help="Identificador opcional del manual cuando se usa --source-chunks.",
    )
    parser.add_argument(
        "--retry-profile",
        choices=["standard", "rate-limit-drain", "micro-batch-recovery"],
        default="standard",
        help="Perfil de reintentos a propagar al extractor A-Box.",
    )
    return parser.parse_args()


def ensure_file_exists(path: Path, message: str) -> None:
    if not path.exists():
        raise SystemExit(message)


def ensure_runtime_prerequisites() -> None:
    ensure_file_exists(OPERATIONAL_TBOX_PATH, f"Falta la T-Box operativa canonica: {OPERATIONAL_TBOX_PATH}")
    if not SCHEMA_CONDENSED_PATH.exists():
        raise SystemExit(f"Falta el esquema condensado operativo: {SCHEMA_CONDENSED_PATH}")



def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def report_success(summary: dict) -> bool:
    total = summary.get("total_questions")
    success = summary.get("correct_answers", summary.get("successful_questions"))
    return isinstance(total, int) and total > 0 and success == total


def is_predominantly_english(language_summary: dict) -> bool:
    counts = language_summary.get("language_counts", {})
    english = counts.get("en", 0)
    spanish = counts.get("es", 0)
    return english > 0 and english >= spanish


def build_blocked_onboarding_result(
    *,
    profile,
    source_chunks: Path,
    baseline_raw_merged_exists: bool,
    stage_records: list[dict],
    blocking_issue: str,
    language_summary: dict,
    failure_detail: str | None = None,
) -> dict:
    onboarding_report = {
        "summary": {
            "manual_id": profile.manual_id,
            "artifact_prefix": profile.artifact_prefix,
            "source_path": str(source_chunks),
            "baseline_raw_merged_exists": baseline_raw_merged_exists,
            "published_to_operational_runtime": False,
            "blocked_before_extraction": False,
            "blocked_during_stage": stage_records[-1]["label"] if stage_records else None,
            "blocking_issue": blocking_issue,
            "failure_detail": failure_detail,
            "source_language_counts": language_summary.get("language_counts", {}),
            "source_language_avg_confidence": language_summary.get("avg_confidence"),
        },
        "paths": {
            "density_report": str(profile.density_report_path),
            "language_detection_report": str(profile.language_detection_report_path),
            "abox_input": str(profile.abox_input_path),
        },
        "stages": stage_records,
    }
    write_json(profile.onboarding_report_path, onboarding_report)
    return {
        "mode": "pilot_onboarding",
        "profile": profile,
        "stages": stage_records,
        "report": onboarding_report,
        "blocked": True,
        "blocking_issue": blocking_issue,
    }


def run_stage(stage_path: Path, extra_args: list[str] | None = None, *, label: str | None = None) -> dict:
    cmd = [sys.executable, str(stage_path)]
    if extra_args:
        cmd.extend(extra_args)
    display = label or str(stage_path.relative_to(REPO_ROOT))
    print(f"\n[operational-build] Ejecutando: {display}")
    started_at = time.time()
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    duration_seconds = round(time.time() - started_at, 3)
    stage_record = {
        "label": display,
        "script": str(stage_path.relative_to(REPO_ROOT)),
        "args": extra_args or [],
        "returncode": result.returncode,
        "duration_seconds": duration_seconds,
    }
    if result.returncode != 0:
        raise SystemExit(f"La fase fallo con codigo {result.returncode}: {stage_path}")
    return stage_record


def resolve_manual_id(source_chunks: Path, manual_id: str) -> str:
    if manual_id.strip():
        return manual_id.strip()
    return source_chunks.stem.replace("chunks_", "")


def build_default_runtime(stages: list[Path], mode: str, retry_profile: str) -> dict:
    stage_records: list[dict] = []
    stage_records.append(run_stage(stages[0], None, label="abox_input_builder"))
    run_stage_args = [
        (stages[1], ["--mode", mode, "--retry-profile", retry_profile], "abox_extractor"),
        (stages[2], None, "abox_merger"),
        (stages[3], None, "abox_canonicalizer"),
        (stages[4], None, "abox_graph_enricher"),
        (stages[5], None, "abox_link_completer"),
        (stages[6], None, "multilingual_lexicon_builder"),
    ]
    for stage_path, extra_args, label in run_stage_args:
        stage_records.append(run_stage(stage_path, extra_args, label=label))

    ensure_file_exists(OPERATIONAL_ABOX_INPUT_PATH, f"No se genero el input operativo A-Box: {OPERATIONAL_ABOX_INPUT_PATH}")
    ensure_file_exists(RAW_MERGED_ABOX_PATH, f"No se genero la A-Box merged bruta: {RAW_MERGED_ABOX_PATH}")
    ensure_file_exists(CANONICAL_ABOX_PATH, f"No se genero la A-Box canonica: {CANONICAL_ABOX_PATH}")
    ensure_file_exists(ENRICHED_ABOX_PATH, f"No se genero la A-Box enriquecida: {ENRICHED_ABOX_PATH}")
    ensure_file_exists(OPERATIONAL_ABOX_PATH, f"No se genero la A-Box linked final: {OPERATIONAL_ABOX_PATH}")
    ensure_file_exists(MULTILINGUAL_LEXICON_PATH, f"No se genero el lexicon multilingue: {MULTILINGUAL_LEXICON_PATH}")
    return {"mode": "default_runtime", "stages": stage_records}


def build_quick_ref_pilot(stages: list[Path], mode: str, source_chunks: Path, manual_id: str, retry_profile: str) -> dict:
    profile = build_onboarding_profile(manual_id, source_chunks)
    baseline_raw_merged_exists = RAW_MERGED_ABOX_PATH.exists()
    stage_records: list[dict] = []

    density_stage = REPO_ROOT / "src" / "1_ingestion" / "density_analyzer.py"
    stage_records.append(
        run_stage(
            density_stage,
            [
                "--input",
                str(source_chunks),
                "--manual-id",
                profile.manual_id,
                "--output",
                str(profile.density_report_path),
                "--language-report-path",
                str(profile.language_detection_report_path),
            ],
            label=f"{profile.artifact_prefix}_density_analyzer",
        )
    )
    ensure_file_exists(profile.density_report_path, f"No se genero el density report piloto: {profile.density_report_path}")
    ensure_file_exists(profile.language_detection_report_path, f"No se genero el language report piloto: {profile.language_detection_report_path}")

    stage_records.append(
        run_stage(
            stages[0],
            [
                "--density-report",
                str(profile.density_report_path),
                "--output",
                str(profile.abox_input_path),
                "--manual-id",
                profile.manual_id,
            ],
            label=f"{profile.artifact_prefix}_abox_input_builder",
        )
    )
    ensure_file_exists(profile.abox_input_path, f"No se genero el A-Box input piloto: {profile.abox_input_path}")
    language_summary = json.loads(profile.language_detection_report_path.read_text(encoding="utf-8"))

    try:
        stage_records.append(
            run_stage(
                stages[1],
                [
                    "--mode",
                    mode,
                    "--retry-profile",
                    retry_profile,
                    "--abox-input",
                    str(profile.abox_input_path),
                    "--manifest-path",
                    str(profile.abox_manifest_path),
                    "--output-dir",
                    str(profile.abox_chunks_dir),
                    "--debug-dir",
                    str(profile.abox_debug_dir),
                ],
                label=f"{profile.artifact_prefix}_abox_extractor",
            )
        )
    except SystemExit as exc:
        return build_blocked_onboarding_result(
            profile=profile,
            source_chunks=source_chunks,
            baseline_raw_merged_exists=baseline_raw_merged_exists,
            stage_records=stage_records,
            blocking_issue="extractor_failed",
            language_summary=language_summary,
            failure_detail=str(exc),
        )

    stage_records.append(
        run_stage(
            stages[2],
            [
                "--input-dir",
                str(profile.abox_chunks_dir),
                "--output",
                str(profile.raw_merged_abox_path),
            ],
            label=f"{profile.artifact_prefix}_abox_merger",
        )
    )
    ensure_file_exists(profile.raw_merged_abox_path, f"No se genero la A-Box merged piloto: {profile.raw_merged_abox_path}")

    publication_args = ["--input-graphs"]
    if baseline_raw_merged_exists:
        publication_args.append(str(RAW_MERGED_ABOX_PATH))
    publication_args.extend([str(profile.raw_merged_abox_path), "--output", str(RAW_MERGED_ABOX_PATH)])
    stage_records.append(
        run_stage(
            stages[2],
            publication_args,
            label=f"{profile.artifact_prefix}_publish_raw_merge",
        )
    )
    ensure_file_exists(RAW_MERGED_ABOX_PATH, f"No se genero la A-Box merged bruta publicada: {RAW_MERGED_ABOX_PATH}")

    stage_records.append(
        run_stage(
            stages[3],
            ["--input", str(RAW_MERGED_ABOX_PATH), "--output", str(CANONICAL_ABOX_PATH)],
            label="abox_canonicalizer",
        )
    )
    ensure_file_exists(CANONICAL_ABOX_PATH, f"No se genero la A-Box canonica: {CANONICAL_ABOX_PATH}")

    stage_records.append(
        run_stage(
            stages[4],
            ["--input", str(CANONICAL_ABOX_PATH), "--output", str(ENRICHED_ABOX_PATH)],
            label="abox_graph_enricher",
        )
    )
    ensure_file_exists(ENRICHED_ABOX_PATH, f"No se genero la A-Box enriquecida: {ENRICHED_ABOX_PATH}")

    stage_records.append(
        run_stage(
            stages[5],
            ["--input", str(ENRICHED_ABOX_PATH), "--output", str(OPERATIONAL_ABOX_PATH)],
            label="abox_link_completer",
        )
    )
    ensure_file_exists(OPERATIONAL_ABOX_PATH, f"No se genero la A-Box linked final: {OPERATIONAL_ABOX_PATH}")

    stage_records.append(
        run_stage(
            stages[6],
            ["--abox-file", str(OPERATIONAL_ABOX_PATH), "--output", str(MULTILINGUAL_LEXICON_PATH)],
            label="multilingual_lexicon_builder",
        )
    )
    ensure_file_exists(MULTILINGUAL_LEXICON_PATH, f"No se genero el lexicon multilingue: {MULTILINGUAL_LEXICON_PATH}")

    language_summary = json.loads(profile.language_detection_report_path.read_text(encoding="utf-8"))
    onboarding_report = {
        "summary": {
            "manual_id": profile.manual_id,
            "artifact_prefix": profile.artifact_prefix,
            "source_path": str(source_chunks),
            "baseline_raw_merged_exists": baseline_raw_merged_exists,
            "published_to_operational_runtime": True,
            "source_language_counts": language_summary.get("language_counts", {}),
            "source_language_avg_confidence": language_summary.get("avg_confidence"),
        },
        "paths": {
            "density_report": str(profile.density_report_path),
            "language_detection_report": str(profile.language_detection_report_path),
            "abox_input": str(profile.abox_input_path),
            "abox_manifest": str(profile.abox_manifest_path),
            "abox_chunks_dir": str(profile.abox_chunks_dir),
            "abox_debug_dir": str(profile.abox_debug_dir),
            "raw_merged_pilot": str(profile.raw_merged_abox_path),
            "raw_merged_operational": str(RAW_MERGED_ABOX_PATH),
            "canonical_abox": str(CANONICAL_ABOX_PATH),
            "enriched_abox": str(ENRICHED_ABOX_PATH),
            "linked_abox": str(OPERATIONAL_ABOX_PATH),
            "multilingual_lexicon": str(MULTILINGUAL_LEXICON_PATH),
        },
        "stages": stage_records,
    }
    write_json(profile.onboarding_report_path, onboarding_report)
    return {"mode": "pilot_onboarding", "profile": profile, "stages": stage_records, "report": onboarding_report}


def run_validation_suite(profile=None) -> dict:
    evaluator = REPO_ROOT / "src" / "8_retrieval" / "qa_evaluator.py"
    validation_records: list[dict] = []

    validation_records.append(
        run_stage(
            evaluator,
            ["--qa-file", str(QA_CANONICAL_PATH)],
            label="qa_evaluator_canonical",
        )
    )
    validation_records.append(
        run_stage(
            evaluator,
            ["--qa-file", str(QA_MULTIHOP_PATH)],
            label="qa_evaluator_multihop",
        )
    )
    if profile is not None and profile.bilingual_dataset_path and profile.bilingual_eval_report_path and profile.bilingual_debug_report_path:
        validation_records.append(
            run_stage(
                evaluator,
                [
                    "--qa-file",
                    str(profile.bilingual_dataset_path),
                    "--report-path",
                    str(profile.bilingual_eval_report_path),
                    "--failure-analysis-path",
                    str(profile.integration_decision_report_path),
                    "--debug-report-path",
                    str(profile.bilingual_debug_report_path),
                ],
                label=f"{profile.artifact_prefix}_qa_evaluator_bilingual",
            )
        )
    ensure_file_exists(GENERALIZATION_EVAL_REPORT_PATH, f"No se genero el reporte canonical: {GENERALIZATION_EVAL_REPORT_PATH}")
    ensure_file_exists(MULTIHOP_EVAL_REPORT_PATH, f"No se genero el reporte multihop: {MULTIHOP_EVAL_REPORT_PATH}")
    if (
        profile is not None
        and profile.bilingual_dataset_path
        and profile.bilingual_eval_report_path
        and profile.bilingual_debug_report_path
    ):
        ensure_file_exists(profile.bilingual_eval_report_path, f"No se genero el reporte bilingue quick ref: {profile.bilingual_eval_report_path}")
        ensure_file_exists(profile.bilingual_debug_report_path, f"No se genero el debug bilingue quick ref: {profile.bilingual_debug_report_path}")
    return {"validation_stages": validation_records}


def finalize_quick_ref_decision(profile, onboarding_result: dict) -> None:
    canonical_eval = json.loads(GENERALIZATION_EVAL_REPORT_PATH.read_text(encoding="utf-8"))
    multihop_eval = json.loads(MULTIHOP_EVAL_REPORT_PATH.read_text(encoding="utf-8"))
    bilingual_eval = json.loads(profile.bilingual_eval_report_path.read_text(encoding="utf-8"))
    language_summary = json.loads(profile.language_detection_report_path.read_text(encoding="utf-8"))

    manual_detected_as_english = is_predominantly_english(language_summary)
    onboarding_ok = manual_detected_as_english and bilingual_eval.get("summary", {}).get("successful_pairs") == bilingual_eval.get("summary", {}).get("total_pairs")
    canonical_ok = report_success(canonical_eval.get("summary", {}))
    multihop_ok = report_success(multihop_eval.get("summary", {}))
    ready_for_next_manual = bool(onboarding_ok and canonical_ok and multihop_ok)

    decision_report = {
        "summary": {
            "manual_id": profile.manual_id,
            "source_path": str(profile.source_path),
            "onboarding_completed": True,
            "manual_detected_as_english": manual_detected_as_english,
            "canonical_regression_ok": canonical_ok,
            "multihop_regression_ok": multihop_ok,
            "bilingual_pairs_total": bilingual_eval.get("summary", {}).get("total_pairs"),
            "bilingual_pairs_successful": bilingual_eval.get("summary", {}).get("successful_pairs"),
            "ready_for_next_manual": ready_for_next_manual,
        },
        "validation": {
            "canonical_report": canonical_eval.get("summary", {}),
            "multihop_report": multihop_eval.get("summary", {}),
            "quick_ref_bilingual_report": bilingual_eval.get("summary", {}),
        },
        "onboarding_paths": onboarding_result["report"]["paths"],
        "remaining_blockers": [] if ready_for_next_manual else [
            blocker
            for blocker, is_active in {
                "canonical_regression": not canonical_ok,
                "multihop_regression": not multihop_ok,
                "quick_ref_bilingual_gap": not onboarding_ok,
            }.items()
            if is_active
        ],
        "recommended_next_change": "second_manual_onboarding" if ready_for_next_manual else "quick_ref_onboarding_followup_minor",
    }
    write_json(profile.integration_decision_report_path, decision_report)


def finalize_blocked_quick_ref_decision(profile, onboarding_result: dict) -> None:
    language_summary = json.loads(profile.language_detection_report_path.read_text(encoding="utf-8"))
    manual_detected_as_english = is_predominantly_english(language_summary)
    bilingual_summary = {}
    if profile.bilingual_eval_report_path and profile.bilingual_eval_report_path.exists():
        bilingual_summary = json.loads(profile.bilingual_eval_report_path.read_text(encoding="utf-8")).get("summary", {})
    blocking_issue = onboarding_result.get("blocking_issue")
    blockers = [blocking_issue] if blocking_issue else []
    if not manual_detected_as_english:
        blockers.append("source_not_predominantly_english")
    decision_report = {
        "summary": {
            "manual_id": profile.manual_id,
            "source_path": str(profile.source_path),
            "onboarding_completed": False,
            "manual_detected_as_english": manual_detected_as_english,
            "published_to_operational_runtime": False,
            "ready_for_next_manual": False,
        },
        "validation": {
            "quick_ref_bilingual_report": bilingual_summary,
        },
        "onboarding_paths": onboarding_result["report"]["paths"],
        "failure_detail": onboarding_result["report"].get("summary", {}).get("failure_detail"),
        "remaining_blockers": blockers,
        "recommended_next_change": (
            "fix_extraction_credentials_then_rerun_pilot"
            if blocking_issue in {"extractor_failed"}
            else "rerun_pilot"
        ),
    }
    write_json(profile.integration_decision_report_path, decision_report)


def should_finalize_bilingual_decision(profile) -> bool:
    return bool(
        profile is not None
        and profile.bilingual_dataset_path is not None
        and profile.bilingual_eval_report_path is not None
        and profile.integration_decision_report_path is not None
    )


def main() -> None:
    args = parse_args()
    entrypoint = Path(OPERATIONAL_BUILD_PIPELINE["entrypoint"])
    stages = [Path(stage) for stage in OPERATIONAL_BUILD_PIPELINE["stages"]]

    if entrypoint.resolve() != Path(__file__).resolve():
        raise SystemExit("El contrato operativo no apunta al entrypoint actual del build.")

    ensure_runtime_prerequisites()

    onboarding_result = None
    if args.source_chunks is not None:
        resolved_source = args.source_chunks.resolve()
        ensure_file_exists(resolved_source, f"Falta el manual/chunks de onboarding: {resolved_source}")
        manual_id = resolve_manual_id(resolved_source, args.manual_id)
        onboarding_result = build_quick_ref_pilot(stages, args.mode, resolved_source, manual_id, args.retry_profile)
    else:
        onboarding_result = build_default_runtime(stages, args.mode, args.retry_profile)

    validation_result = {"validation_stages": []}
    if onboarding_result.get("blocked"):
        if should_finalize_bilingual_decision(onboarding_result.get("profile")):
            finalize_blocked_quick_ref_decision(onboarding_result["profile"], onboarding_result)
    else:
        validation_result = run_validation_suite(onboarding_result.get("profile") if isinstance(onboarding_result, dict) else None)
        if should_finalize_bilingual_decision(onboarding_result.get("profile")):
            finalize_quick_ref_decision(onboarding_result["profile"], onboarding_result)

    profile = onboarding_result.get("profile") if isinstance(onboarding_result, dict) else None
    display_abox_input = profile.abox_input_path if profile is not None else OPERATIONAL_ABOX_INPUT_PATH

    print("\n[operational-build] Build operativo completado.")
    print(f"- T-Box: {OPERATIONAL_TBOX_PATH}")
    print(f"- A-Box input: {display_abox_input}")
    print(f"- A-Box merged bruta: {RAW_MERGED_ABOX_PATH}")
    print(f"- A-Box canonica: {CANONICAL_ABOX_PATH}")
    print(f"- A-Box enriquecida: {ENRICHED_ABOX_PATH}")
    print(f"- A-Box operativa linked: {OPERATIONAL_ABOX_PATH}")
    print(f"- Lexicon multilingue ES/EN: {MULTILINGUAL_LEXICON_PATH}")
    print(f"- Validaciones ejecutadas: {len(validation_result['validation_stages'])}")
    if profile is not None:
        print(f"- Onboarding piloto: {profile.source_path}")
        print(f"- Reporte onboarding: {profile.onboarding_report_path}")
        print(f"- Decision quick ref: {profile.integration_decision_report_path}")
        if onboarding_result.get("blocked"):
            print(f"- Estado onboarding: bloqueado por {onboarding_result['blocking_issue']}")
    print(f"- Modo extractor: {args.mode}")
    print(f"- Retry profile: {args.retry_profile}")


if __name__ == "__main__":
    main()
