from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from artifact_contracts import CANONICAL_ABOX_PATH, ENRICHED_ABOX_PATH, OPERATIONAL_ABOX_INPUT_PATH, OPERATIONAL_ABOX_PATH, OPERATIONAL_BUILD_PIPELINE, OPERATIONAL_TBOX_PATH, RAW_MERGED_ABOX_PATH

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_MODE = "resume-compatible"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Entrypoint del build operativo canonico, enriquecido y linked.")
    parser.add_argument(
        "--mode",
        choices=["resume-compatible", "force-stale", "force-all"],
        default=DEFAULT_MODE,
        help="Modo de ejecucion para la extraccion A-Box.",
    )
    return parser.parse_args()


def ensure_file_exists(path: Path, message: str) -> None:
    if not path.exists():
        raise SystemExit(message)


def ensure_runtime_prerequisites() -> None:
    ensure_file_exists(OPERATIONAL_TBOX_PATH, f"Falta la T-Box operativa canonica: {OPERATIONAL_TBOX_PATH}")
    if not os.environ.get("MISTRAL_API_KEY"):
        raise SystemExit("Falta MISTRAL_API_KEY. El build operativo necesita credenciales antes de lanzar la extraccion A-Box.")


def run_stage(stage_path: Path, extra_args: list[str] | None = None) -> None:
    cmd = [sys.executable, str(stage_path)]
    if extra_args:
        cmd.extend(extra_args)
    print(f"\n[operational-build] Ejecutando: {stage_path.relative_to(REPO_ROOT)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        raise SystemExit(f"La fase fallo con codigo {result.returncode}: {stage_path}")


def main() -> None:
    args = parse_args()
    entrypoint = Path(OPERATIONAL_BUILD_PIPELINE["entrypoint"])
    stages = [Path(stage) for stage in OPERATIONAL_BUILD_PIPELINE["stages"]]

    if entrypoint.resolve() != Path(__file__).resolve():
        raise SystemExit("El contrato operativo no apunta al entrypoint actual del build.")

    ensure_runtime_prerequisites()

    run_stage(stages[0])
    ensure_file_exists(OPERATIONAL_ABOX_INPUT_PATH, f"No se genero el input operativo A-Box: {OPERATIONAL_ABOX_INPUT_PATH}")
    run_stage(stages[1], ["--mode", args.mode])
    run_stage(stages[2])
    ensure_file_exists(RAW_MERGED_ABOX_PATH, f"No se genero la A-Box merged bruta: {RAW_MERGED_ABOX_PATH}")
    run_stage(stages[3])
    ensure_file_exists(CANONICAL_ABOX_PATH, f"No se genero la A-Box canonica: {CANONICAL_ABOX_PATH}")
    run_stage(stages[4])
    ensure_file_exists(ENRICHED_ABOX_PATH, f"No se genero la A-Box enriquecida: {ENRICHED_ABOX_PATH}")
    run_stage(stages[5])
    ensure_file_exists(OPERATIONAL_ABOX_PATH, f"No se genero la A-Box linked final: {OPERATIONAL_ABOX_PATH}")

    print("\n[operational-build] Build operativo completado.")
    print(f"- T-Box: {OPERATIONAL_TBOX_PATH}")
    print(f"- A-Box input: {OPERATIONAL_ABOX_INPUT_PATH}")
    print(f"- A-Box merged bruta: {RAW_MERGED_ABOX_PATH}")
    print(f"- A-Box canonica: {CANONICAL_ABOX_PATH}")
    print(f"- A-Box enriquecida: {ENRICHED_ABOX_PATH}")
    print(f"- A-Box operativa linked: {OPERATIONAL_ABOX_PATH}")
    print(f"- Modo extractor: {args.mode}")


if __name__ == "__main__":
    main()
