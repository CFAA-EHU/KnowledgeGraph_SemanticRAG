from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping

LANGUAGE_STOPWORDS = {
    "es": {
        "de", "la", "el", "los", "las", "para", "segun", "seguridad", "manual",
        "maquina", "mantenimiento", "capitulo", "seccion", "pagina", "indicacion",
        "advertencia", "componentes", "repuestos", "funcionamiento", "direccion",
    },
    "en": {
        "the", "and", "for", "with", "what", "which", "manual", "machine",
        "maintenance", "safety", "section", "pages", "figure", "address",
        "email", "support", "replacement", "component", "does", "require",
    },
}

HEADER_HINTS = {
    "es": {"paginas", "páginas", "seccion", "sección", "titulo", "título", "capitulo", "capítulo"},
    "en": {"pages", "page", "section", "title", "chapter"},
}


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9@/_\-.]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def tokenize(text: str) -> list[str]:
    return [token for token in normalize_text(text).split() if token]


def score_language(text: str, *, metadata: Iterable[str] | None = None) -> dict[str, Any]:
    tokens = tokenize(text)
    metadata_tokens = tokenize(" ".join(metadata or []))
    counts = {"es": 0.0, "en": 0.0}

    for language, stopwords in LANGUAGE_STOPWORDS.items():
        token_hits = sum(1 for token in tokens if token in stopwords)
        header_hits = sum(1 for token in metadata_tokens if token in HEADER_HINTS[language])
        counts[language] = float(token_hits) + header_hits * 1.5

    # Strong lexical cues that appear frequently in onboarding material.
    normalized = " ".join(tokens + metadata_tokens)
    if re.search(r"\b(que|segun|maquina|mantenimiento|seguridad|capitulo|pagina)\b", normalized):
        counts["es"] += 2.0
    if re.search(r"\b(what|which|machine|maintenance|safety|chapter|page|pages)\b", normalized):
        counts["en"] += 2.0

    total = counts["es"] + counts["en"]
    if total == 0:
        return {"language": "es", "confidence": 0.51, "scores": counts}

    best_language = "es" if counts["es"] >= counts["en"] else "en"
    margin = abs(counts["es"] - counts["en"])
    confidence = min(0.99, 0.55 + (margin / max(total, 1.0)) * 0.4)
    return {"language": best_language, "confidence": round(confidence, 4), "scores": counts}


def detect_language(text: str, *, metadata: Iterable[str] | None = None) -> tuple[str, float]:
    report = score_language(text, metadata=metadata)
    return report["language"], float(report["confidence"])


def iter_term_surfaces(term_entry: Mapping[str, Any], language: str | None = None) -> list[str]:
    surfaces: list[str] = []
    for key in ("termino", "surface_es", "surface_en"):
        value = term_entry.get(key)
        if isinstance(value, str) and value.strip():
            surfaces.append(value.strip())
    aliases = term_entry.get("aliases", [])
    if isinstance(aliases, list):
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                surfaces.append(alias.strip())
    if language == "es" and isinstance(term_entry.get("surface_es"), str):
        surfaces.insert(0, term_entry["surface_es"].strip())
    if language == "en" and isinstance(term_entry.get("surface_en"), str):
        surfaces.insert(0, term_entry["surface_en"].strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for surface in surfaces:
        key = normalize_text(surface)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(surface)
    return deduped
