import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import json

from artifact_contracts import DENSITY_REPORT_PATH, OPERATIONAL_ABOX_INPUT_PATH, build_abox_chunk_hash


def load_density_report() -> list[dict]:
    if not DENSITY_REPORT_PATH.exists():
        raise FileNotFoundError(f"Archivo requerido no encontrado: {DENSITY_REPORT_PATH}")
    with open(DENSITY_REPORT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("density_report.json debe contener una lista de chunks.")
    return data


def build_abox_input_entry(chunk: dict) -> dict | None:
    texto_fuente = (chunk.get("texto") or "").strip()
    if not texto_fuente:
        return None

    entry = {
        "chunk_id": chunk["chunk_id"],
        "texto_fuente": texto_fuente,
        "paginas": chunk.get("paginas", ""),
        "seccion": chunk.get("seccion", ""),
        "titulo": chunk.get("titulo", ""),
        "density_level": chunk.get("density_level", ""),
        "terms_found": chunk.get("terms_found", []),
        "source_path": str(DENSITY_REPORT_PATH),
    }
    entry["chunk_hash"] = build_abox_chunk_hash(entry)
    return entry


def build_abox_input_payload(chunks: list[dict]) -> list[dict]:
    payload = []
    for chunk in chunks:
        entry = build_abox_input_entry(chunk)
        if entry is not None:
            payload.append(entry)
    return payload


def save_abox_input(payload: list[dict]) -> None:
    OPERATIONAL_ABOX_INPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OPERATIONAL_ABOX_INPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> None:
    chunks = load_density_report()
    payload = build_abox_input_payload(chunks)
    save_abox_input(payload)
    print(f"A-Box input operativo generado con {len(payload)} chunks en {OPERATIONAL_ABOX_INPUT_PATH}")


if __name__ == "__main__":
    main()
