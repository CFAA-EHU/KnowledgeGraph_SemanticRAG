import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
INGESTION_DIR = REPO_ROOT / "src" / "1_ingestion"
if str(INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(INGESTION_DIR))

import argparse
import json

from artifact_contracts import DENSITY_REPORT_PATH, OPERATIONAL_ABOX_INPUT_PATH, build_abox_chunk_hash
from language_utils import detect_language


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the operational A-Box input payload from a density report.")
    parser.add_argument("--density-report", type=Path, default=DENSITY_REPORT_PATH, help="Ruta del density report de entrada.")
    parser.add_argument("--output", type=Path, default=OPERATIONAL_ABOX_INPUT_PATH, help="Ruta de salida del A-Box input.")
    parser.add_argument("--manual-id", default="", help="Identificador opcional del manual para trazabilidad.")
    return parser.parse_args()


def load_density_report(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Archivo requerido no encontrado: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("density_report.json debe contener una lista de chunks.")
    return data


def build_abox_input_entry(chunk: dict, *, density_report_path: Path, manual_id: str | None = None) -> dict | None:
    texto_fuente = (chunk.get("texto") or "").strip()
    if not texto_fuente:
        return None
    detected_language, detected_confidence = detect_language(
        texto_fuente,
        metadata=[chunk.get("paginas", ""), chunk.get("seccion", ""), chunk.get("titulo", "")],
    )

    entry = {
        "chunk_id": chunk["chunk_id"],
        "manual_id": chunk.get("manual_id") or manual_id,
        "texto_fuente": texto_fuente,
        "paginas": chunk.get("paginas", ""),
        "seccion": chunk.get("seccion", ""),
        "titulo": chunk.get("titulo", ""),
        "density_level": chunk.get("density_level", ""),
        "terms_found": chunk.get("terms_found", []),
        "source_language": chunk.get("source_language") or detected_language,
        "language_confidence": chunk.get("language_confidence") or detected_confidence,
        "source_path": chunk.get("source_path") or str(density_report_path),
    }
    entry["chunk_hash"] = build_abox_chunk_hash(entry)
    return entry


def build_abox_input_payload(chunks: list[dict], *, density_report_path: Path, manual_id: str | None = None) -> list[dict]:
    payload = []
    for chunk in chunks:
        entry = build_abox_input_entry(chunk, density_report_path=density_report_path, manual_id=manual_id)
        if entry is not None:
            payload.append(entry)
    return payload


def save_abox_input(payload: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> None:
    args = parse_args()
    chunks = load_density_report(args.density_report)
    payload = build_abox_input_payload(chunks, density_report_path=args.density_report, manual_id=args.manual_id or None)
    save_abox_input(payload, args.output)
    print(f"A-Box input operativo generado con {len(payload)} chunks en {args.output}")


if __name__ == "__main__":
    main()
