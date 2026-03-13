"""
density_analyzer.py
Análisis de densidad y segmentación física de textos con solapamiento semántico.
"""

import sys
import json
import argparse
import re
from pathlib import Path

import spacy
import tiktoken

sys.path.insert(0, str(Path(__file__).resolve().parent))
from termLoader import get_terms

CHUNK_SIZE_HIGH_DENSITY = 256
CHUNK_SIZE_LOW_DENSITY  = 512
OVERLAP_RATIO           = 0.15
HIGH_DENSITY_THRESHOLD  = 0.05

try:
    nlp = spacy.load("es_core_news_sm", exclude=["ner", "parser"])
    nlp.add_pipe("sentencizer")
except OSError:
    print("Error: Modelo es_core_news_sm no encontrado.")
    sys.exit(1)

TOKENIZER = tiktoken.get_encoding("cl100k_base")

def parse_chunks(filepath: str) -> list[dict]:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {filepath}")

    content = path.read_text(encoding="utf-8")
    header_pattern = re.compile(
        r"---\s*Páginas:\s*(\[.*?\])\s*\|\s*Sección:\s*(.*?)\s*\|\s*Título:\s*(.*?)\s*---"
    )

    chunks = []
    parts = header_pattern.split(content)

    i = 1
    while i + 3 <= len(parts):
        chunks.append({
            "paginas": parts[i].strip(),
            "seccion": parts[i + 1].strip(),
            "titulo":  parts[i + 2].strip(),
            "texto":   parts[i + 3].strip() if i + 3 < len(parts) else "",
        })
        i += 4

    return chunks

def count_technical_terms(text: str, terms: list[dict]) -> tuple[int, list[str]]:
    text_lower = text.lower()
    found = []
    for item in terms:
        term = item["termino"]
        pattern = r'\b' + re.escape(term.lower()) + r'\b'
        if re.search(pattern, text_lower):
            found.append(term)
    return len(found), found

def calculate_density(text: str, terms: list[dict]) -> float:
    words = text.split()
    if not words:
        return 0.0
    term_count, _ = count_technical_terms(text, terms)
    return round(term_count / len(words), 4)

def get_chunk_config(density: float) -> dict:
    is_high = density >= HIGH_DENSITY_THRESHOLD
    chunk_size = CHUNK_SIZE_HIGH_DENSITY if is_high else CHUNK_SIZE_LOW_DENSITY
    return {
        "density_level":     "alta" if is_high else "baja",
        "chunk_size_tokens": chunk_size,
        "overlap_tokens":    round(chunk_size * OVERLAP_RATIO),
    }

def split_text_sentence_safe(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Fragmenta físicamente el texto respetando oraciones y aplicando solapamiento."""
    doc = nlp(text)
    sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
    
    if not sentences:
        return []

    chunks = []
    current_chunk_sentences = []
    current_tokens = 0

    i = 0
    while i < len(sentences):
        sentence = sentences[i]
        sent_tokens = len(TOKENIZER.encode(sentence))

        if current_tokens + sent_tokens > max_tokens and current_chunk_sentences:
            chunks.append(" ".join(current_chunk_sentences))
            
            overlap_buffer = []
            overlap_count = 0
            for prev_sent in reversed(current_chunk_sentences):
                prev_tokens = len(TOKENIZER.encode(prev_sent))
                if overlap_count + prev_tokens <= overlap_tokens:
                    overlap_buffer.insert(0, prev_sent)
                    overlap_count += prev_tokens
                else:
                    break
            
            current_chunk_sentences = overlap_buffer
            current_tokens = overlap_count

        current_chunk_sentences.append(sentence)
        current_tokens += sent_tokens
        i += 1

    if current_chunk_sentences:
        chunks.append(" ".join(current_chunk_sentences))

    return chunks

def analyze(filepath: str, terms: list[dict]) -> list[dict]:
    raw_chunks = parse_chunks(filepath)
    report = []
    global_chunk_id = 1

    for chunk in raw_chunks:
        texto_base = chunk["texto"]
        if not texto_base:
            continue

        density = calculate_density(texto_base, terms)
        config  = get_chunk_config(density)
        
        # Ejecución del particionado físico
        sub_textos = split_text_sentence_safe(
            texto_base, 
            config["chunk_size_tokens"], 
            config["overlap_tokens"]
        )

        for sub_texto in sub_textos:
            count, found_terms = count_technical_terms(sub_texto, terms)
            
            report.append({
                "chunk_id":              global_chunk_id,
                "paginas":               chunk["paginas"],
                "seccion":               chunk["seccion"],
                "titulo":                chunk["titulo"],
                "texto":                 sub_texto,
                "text_preview":          sub_texto[:100] + "..." if len(sub_texto) > 100 else sub_texto,
                "word_count":            len(sub_texto.split()),
                "token_count":           len(TOKENIZER.encode(sub_texto)),
                "technical_terms_count": count,
                "terms_found":           found_terms,
                "density_score":         density, 
                **config,
            })
            global_chunk_id += 1

    return report

def print_summary(report: list[dict], total_terms: int):
    total = len(report)
    high  = sum(1 for r in report if r["density_level"] == "alta")
    low   = total - high

    print("\n" + "─" * 65)
    print("📊 RESUMEN DEL ANÁLISIS Y SEGMENTACIÓN FÍSICA")
    print("─" * 65)
    print(f"  Términos ontológicos cargados : {total_terms}")
    print(f"  Total sub-chunks generados    : {total}")
    print(f"  Alta densidad (≥{HIGH_DENSITY_THRESHOLD:.0%})         : {high} bloques")
    print(f"  Baja densidad (<{HIGH_DENSITY_THRESHOLD:.0%})          : {low} bloques")
    print("─" * 65)

def save_report(report: list[dict], input_path: str):
    output_path = Path(input_path).parent / "density_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"💾 Reporte segmentado guardado en: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Análisis de densidad y segmentación física")
    parser.add_argument("--input", required=True, help="Ruta al archivo de chunks")
    parser.add_argument("--refresh-terms", action="store_true", help="Forzar regeneración del cache")
    args = parser.parse_args()

    terms = get_terms(filepath=args.input, force_refresh=args.refresh_terms)
    report = analyze(args.input, terms)
    
    print_summary(report, total_terms=len(terms))
    save_report(report, args.input)