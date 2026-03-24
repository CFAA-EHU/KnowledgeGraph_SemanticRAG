from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import spacy
import tiktoken

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(INGESTION_DIR))

from artifact_contracts import LANGUAGE_DETECTION_REPORT_PATH
from language_utils import detect_language, iter_term_surfaces
from termLoader import get_terms

CHUNK_SIZE_HIGH_DENSITY = 256
CHUNK_SIZE_LOW_DENSITY = 512
OVERLAP_RATIO = 0.15
HIGH_DENSITY_THRESHOLD = 0.05

NLP = spacy.blank("xx")
if "sentencizer" not in NLP.pipe_names:
    NLP.add_pipe("sentencizer")

TOKENIZER = tiktoken.get_encoding("cl100k_base")
HEADER_PATTERN = re.compile(
    r"---\s*(?:P[aá]ginas|Pages):\s*(\[.*?\])\s*\|\s*"
    r"(?:Secci[oó]n|Section):\s*(.*?)\s*\|\s*"
    r"(?:T[ií]tulo|Title):\s*(.*?)\s*---",
    re.IGNORECASE | re.DOTALL,
)


def parse_chunks(filepath: str) -> list[dict]:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"No se encontro el archivo: {filepath}")

    content = path.read_text(encoding="utf-8")
    content = re.sub(
        r"(---\s*(?:P[aÃ¡]ginas|Pages):\s*)(?!\[)([^|\n]+?)(\s*\|)",
        lambda match: f"{match.group(1)}[{match.group(2).strip()}]{match.group(3)}",
        content,
        flags=re.IGNORECASE,
    )
    parts = HEADER_PATTERN.split(content)
    chunks: list[dict] = []

    index = 1
    while index + 3 <= len(parts):
        text = parts[index + 3].strip() if index + 3 < len(parts) else ""
        chunks.append(
            {
                "paginas": parts[index].strip(),
                "seccion": parts[index + 1].strip(),
                "titulo": parts[index + 2].strip(),
                "texto": text,
            }
        )
        index += 4

    if not chunks and content.strip():
        chunks.append({"paginas": "[]", "seccion": "", "titulo": "-", "texto": content.strip()})
    return chunks


def count_technical_terms(text: str, terms: list[dict], *, source_language: str) -> tuple[int, list[str]]:
    text_lower = text.lower()
    found: list[str] = []
    for item in terms:
        for surface in iter_term_surfaces(item, source_language):
            pattern = r"\b" + re.escape(surface.lower()) + r"\b"
            if re.search(pattern, text_lower):
                found.append(item.get("termino", surface))
                break
    deduped = list(dict.fromkeys(found))
    return len(deduped), deduped


def calculate_density(text: str, terms: list[dict], *, source_language: str) -> float:
    words = text.split()
    if not words:
        return 0.0
    term_count, _ = count_technical_terms(text, terms, source_language=source_language)
    return round(term_count / len(words), 4)


def get_chunk_config(density: float) -> dict:
    is_high = density >= HIGH_DENSITY_THRESHOLD
    chunk_size = CHUNK_SIZE_HIGH_DENSITY if is_high else CHUNK_SIZE_LOW_DENSITY
    return {
        "density_level": "alta" if is_high else "baja",
        "chunk_size_tokens": chunk_size,
        "overlap_tokens": round(chunk_size * OVERLAP_RATIO),
    }


def split_text_sentence_safe(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    doc = NLP(text)
    sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
    if not sentences:
        return [text.strip()] if text.strip() else []

    chunks: list[str] = []
    current_sentences: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = len(TOKENIZER.encode(sentence))
        if current_sentences and current_tokens + sentence_tokens > max_tokens:
            chunks.append(" ".join(current_sentences))
            overlap_buffer: list[str] = []
            overlap_count = 0
            for previous in reversed(current_sentences):
                previous_tokens = len(TOKENIZER.encode(previous))
                if overlap_count + previous_tokens <= overlap_tokens:
                    overlap_buffer.insert(0, previous)
                    overlap_count += previous_tokens
                else:
                    break
            current_sentences = overlap_buffer
            current_tokens = overlap_count

        current_sentences.append(sentence)
        current_tokens += sentence_tokens

    if current_sentences:
        chunks.append(" ".join(current_sentences))
    return chunks


def analyze(filepath: str, terms: list[dict], *, manual_id: str | None = None) -> tuple[list[dict], dict]:
    raw_chunks = parse_chunks(filepath)
    report: list[dict] = []
    language_rows: list[dict] = []
    global_chunk_id = 1

    for chunk in raw_chunks:
        source_text = chunk["texto"]
        if not source_text:
            continue

        metadata = [chunk.get("paginas", ""), chunk.get("seccion", ""), chunk.get("titulo", "")]
        source_language, language_confidence = detect_language(source_text, metadata=metadata)
        density = calculate_density(source_text, terms, source_language=source_language)
        config = get_chunk_config(density)
        sub_texts = split_text_sentence_safe(source_text, config["chunk_size_tokens"], config["overlap_tokens"])

        for sub_text in sub_texts:
            count, found_terms = count_technical_terms(sub_text, terms, source_language=source_language)
            report.append(
                {
                    "chunk_id": global_chunk_id,
                    "manual_id": manual_id,
                    "source_path": str(Path(filepath).resolve()),
                    "paginas": chunk["paginas"],
                    "seccion": chunk["seccion"],
                    "titulo": chunk["titulo"],
                    "texto": sub_text,
                    "text_preview": sub_text[:100] + "..." if len(sub_text) > 100 else sub_text,
                    "word_count": len(sub_text.split()),
                    "token_count": len(TOKENIZER.encode(sub_text)),
                    "technical_terms_count": count,
                    "terms_found": found_terms,
                    "density_score": density,
                    "source_language": source_language,
                    "language_confidence": language_confidence,
                    **config,
                }
            )
            language_rows.append(
                {
                    "chunk_id": global_chunk_id,
                    "manual_id": manual_id,
                    "source_language": source_language,
                    "language_confidence": language_confidence,
                    "paginas": chunk["paginas"],
                    "seccion": chunk["seccion"],
                    "titulo": chunk["titulo"],
                }
            )
            global_chunk_id += 1

    summary = {
        "manual_id": manual_id,
        "source_file": str(Path(filepath).resolve()),
        "total_chunks": len(report),
        "language_counts": {
            "es": sum(1 for row in language_rows if row["source_language"] == "es"),
            "en": sum(1 for row in language_rows if row["source_language"] == "en"),
        },
        "avg_confidence": round(
            sum(row["language_confidence"] for row in language_rows) / len(language_rows), 4
        )
        if language_rows
        else 0.0,
        "chunks": language_rows,
    }
    return report, summary


def print_summary(report: list[dict], total_terms: int, language_summary: dict) -> None:
    total = len(report)
    high = sum(1 for row in report if row["density_level"] == "alta")
    low = total - high
    print("\n" + "-" * 65)
    print("RESUMEN DEL ANALISIS Y SEGMENTACION FISICA")
    print("-" * 65)
    print(f"  Terminos ontologicos cargados : {total_terms}")
    print(f"  Total sub-chunks generados    : {total}")
    print(f"  Alta densidad (>= {HIGH_DENSITY_THRESHOLD:.0%}) : {high} bloques")
    print(f"  Baja densidad (<  {HIGH_DENSITY_THRESHOLD:.0%}) : {low} bloques")
    print(f"  Idioma es detectado           : {language_summary['language_counts']['es']}")
    print(f"  Idioma en detectado           : {language_summary['language_counts']['en']}")
    print("-" * 65)


def save_report(report: list[dict], input_path: str, language_summary: dict, *, output_path: Path | None = None, language_report_path: Path | None = None) -> None:
    output_path = output_path or (Path(input_path).parent / "density_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    language_report_path = language_report_path or LANGUAGE_DETECTION_REPORT_PATH
    language_report_path.parent.mkdir(parents=True, exist_ok=True)
    language_report_path.write_text(
        json.dumps(language_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Reporte segmentado guardado en: {output_path}")
    print(f"Reporte de deteccion de idioma guardado en: {language_report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analisis de densidad y segmentacion fisica")
    parser.add_argument("--input", required=True, help="Ruta al archivo de chunks")
    parser.add_argument("--manual-id", default="", help="Identificador opcional del manual para trazabilidad de onboarding.")
    parser.add_argument("--output", type=Path, default=None, help="Ruta de salida opcional para el reporte de densidad.")
    parser.add_argument("--language-report-path", type=Path, default=None, help="Ruta de salida opcional para el reporte de deteccion de idioma.")
    parser.add_argument("--refresh-terms", action="store_true", help="Forzar regeneracion del cache")
    args = parser.parse_args()

    terms = get_terms(filepath=args.input, force_refresh=args.refresh_terms)
    report, language_summary = analyze(args.input, terms, manual_id=args.manual_id or None)
    print_summary(report, total_terms=len(terms), language_summary=language_summary)
    save_report(report, args.input, language_summary, output_path=args.output, language_report_path=args.language_report_path)
