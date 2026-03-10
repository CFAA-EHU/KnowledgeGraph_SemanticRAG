<<<<<<< HEAD
print("hello world")
=======
"""
density_analyzer.py
Issue #1 — Análisis de densidad de términos técnicos por chunk.

Usa term_loader.py para obtener los términos técnicos desde
ESDBpedia (español) y AAS/ECLASS (inglés + traducción Helsinki-NLP),
con cacheo local en cache/terms_cache.json.

Uso:
    # Primera ejecución (construye el cache de términos):
    python src/1_ingestion/density_analyzer.py --input data/raw/chunks_manual_instrucciones_a218_reduced.txt

    # Forzar renovación del cache de términos:
    python src/1_ingestion/density_analyzer.py --input data/raw/... --refresh-terms

Salida:
    data/raw/density_report.json
"""

import sys
import json
import argparse
import re
from pathlib import Path

# Asegurar que Python encuentra term_loader aunque se ejecute desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent))
from termLoader import get_terms


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

CHUNK_SIZE_HIGH_DENSITY = 256   # Alta densidad → chunks pequeños
CHUNK_SIZE_LOW_DENSITY  = 512   # Baja densidad → chunks grandes
OVERLAP_RATIO           = 0.15  # Solapamiento del 15%
HIGH_DENSITY_THRESHOLD  = 0.05  # 5 términos técnicos por cada 100 palabras


# ─────────────────────────────────────────────────────────────────────────────
# PARSING DEL ARCHIVO
# ─────────────────────────────────────────────────────────────────────────────

def parse_chunks(filepath: str) -> list[dict]:
    """
    Lee el archivo y separa cada bloque en metadatos + texto.

    Formato esperado:
        --- Páginas: [N] | Sección: X.X | Título: - ---
        Texto del chunk...
    """
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

    print(f"✅ Parseados {len(chunks)} chunks desde {filepath}")
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# ANÁLISIS DE DENSIDAD
# ─────────────────────────────────────────────────────────────────────────────

def count_technical_terms(text: str, terms: list[str]) -> tuple[int, list[str]]:
    """Cuenta términos técnicos encontrados en el texto."""
    text_lower = text.lower()
    found = []
    for term in terms:
        pattern = r'\b' + re.escape(term.lower()) + r'\b'
        if re.search(pattern, text_lower):
            found.append(term)
    return len(found), found


def calculate_density(text: str, terms: list[str]) -> float:
    """Densidad = nº términos técnicos únicos / nº total de palabras."""
    words = text.split()
    if not words:
        return 0.0
    term_count, _ = count_technical_terms(text, terms)
    return round(term_count / len(words), 4)


def get_chunk_config(density: float) -> dict:
    """Devuelve configuración de chunking según nivel de densidad."""
    is_high = density >= HIGH_DENSITY_THRESHOLD
    chunk_size = CHUNK_SIZE_HIGH_DENSITY if is_high else CHUNK_SIZE_LOW_DENSITY
    return {
        "density_level":     "alta" if is_high else "baja",
        "chunk_size_tokens": chunk_size,
        "overlap_tokens":    round(chunk_size * OVERLAP_RATIO),
    }


def analyze(filepath: str, terms: list[str]) -> list[dict]:
    """Analiza todos los chunks y devuelve el reporte completo."""
    raw_chunks = parse_chunks(filepath)
    report = []

    for i, chunk in enumerate(raw_chunks):
        texto   = chunk["texto"]
        density = calculate_density(texto, terms)
        count, found_terms = count_technical_terms(texto, terms)
        config  = get_chunk_config(density)

        report.append({
            "chunk_id":              i + 1,
            "paginas":               chunk["paginas"],
            "seccion":               chunk["seccion"],
            "titulo":                chunk["titulo"],
            "text_preview":          texto[:100] + "..." if len(texto) > 100 else texto,
            "word_count":            len(texto.split()),
            "technical_terms_count": count,
            "terms_found":           found_terms,
            "density_score":         density,
            **config,
        })

    return report


# ─────────────────────────────────────────────────────────────────────────────
# SALIDA
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(report: list[dict], total_terms: int):
    total = len(report)
    high  = sum(1 for r in report if r["density_level"] == "alta")
    low   = total - high

    print("\n" + "─" * 65)
    print("📊 RESUMEN DEL ANÁLISIS DE DENSIDAD")
    print("─" * 65)
    print(f"  Términos ontológicos cargados : {total_terms}")
    print(f"  Total chunks analizados       : {total}")
    print(f"  Alta densidad (≥{HIGH_DENSITY_THRESHOLD:.0%})         : {high} chunks → {CHUNK_SIZE_HIGH_DENSITY} tokens c/u")
    print(f"  Baja densidad (<{HIGH_DENSITY_THRESHOLD:.0%})          : {low} chunks → {CHUNK_SIZE_LOW_DENSITY} tokens c/u")
    print("─" * 65)

    print("\n📋 DETALLE POR CHUNK:\n")
    for r in report:
        print(f"  Chunk #{r['chunk_id']:03d} | Sección: {r['seccion'][:35]:<35} | "
              f"Densidad: {r['density_score']:.2%} | Nivel: {r['density_level'].upper()}")
        print(f"  Términos : {', '.join(r['terms_found']) if r['terms_found'] else '—'}")
        print(f"  Preview  : {r['text_preview']}")
        print()


def save_report(report: list[dict], input_path: str):
    output_path = Path(input_path).parent / "density_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"💾 Reporte guardado en: {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Análisis de densidad técnica por chunk")
    parser.add_argument(
        "--input",
        default="data/raw/chunks_manual_instrucciones_a218_reduced.txt",
        help="Ruta al archivo de chunks"
    )
    parser.add_argument(
        "--refresh-terms",
        action="store_true",
        help="Forzar regeneración del cache de términos ontológicos"
    )
    args = parser.parse_args()

    # 1. Cargar términos técnicos desde ontologías (o cache)
    terms = get_terms(force_refresh=args.refresh_terms)

    # 2. Analizar los chunks
    report = analyze(args.input, terms)

    # 3. Mostrar y guardar resultados
    print_summary(report, total_terms=len(terms))
    save_report(report, args.input)
>>>>>>> 98ca477 (feat(#1): density analyzer completo — ESDBpedia + AAS/Helsinki-NLP + reporte generado)
