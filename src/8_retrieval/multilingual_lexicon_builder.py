from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from artifact_contracts import (
    MULTILINGUAL_LEXICON_PATH,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
)

CACHE_PATH = REPO_ROOT / "cache" / "terms_cache.json"
BASE_URI = "https://vocab.cfaa.eus/broaching/"

CURATED_ENTITY_SURFACES: dict[str, dict[str, list[str]]] = {
    f"{BASE_URI}ManualBrochadoraA218": {
        "es": ["manual de la brochadora A218", "manual A218"],
        "en": ["A218 broaching machine manual", "manual A218"],
    },
    f"{BASE_URI}Maquina_A218_RASHEM_7x3000x500": {
        "es": ["brochadora A218", "maquina A218"],
        "en": ["A218 broaching machine", "A218 machine"],
    },
    f"{BASE_URI}Figura0_1_1InformacionMostradaEnPaginas": {
        "es": ["figura 0-1-1", "informacion mostrada en paginas"],
        "en": ["figure 0-1-1", "information shown on pages"],
    },
    f"{BASE_URI}Empresa_EKIN_S_Coop": {
        "es": ["EKIN", "empresa EKIN", "EKIN S. Coop"],
        "en": ["EKIN", "EKIN company", "EKIN S. Coop"],
    },
    f"{BASE_URI}DepartamentoAsistenciaClienteEKIN": {
        "es": ["departamento de asistencia al cliente de EKIN"],
        "en": ["EKIN customer support department", "EKIN customer service department"],
    },
    f"{BASE_URI}Directiva2006_42_CE": {
        "es": ["directiva 2006/42/CE", "declaracion CE"],
        "en": ["Directive 2006/42/CE", "CE declaration directive"],
    },
    f"{BASE_URI}SistemaSeguridadMaquina": {
        "es": ["sistema de seguridad de la maquina"],
        "en": ["machine safety system"],
    },
    f"{BASE_URI}PlanMantenimientoEKIN": {
        "es": ["plan de mantenimiento", "plan de mantenimiento de EKIN"],
        "en": ["maintenance plan", "EKIN maintenance plan"],
    },
    f"{BASE_URI}MaquinaBrochadoExterior_18": {
        "es": ["maquina de brochado exterior", "brochado exterior"],
        "en": ["external broaching machine"],
    },
    f"{BASE_URI}PiezaRecambio_1": {
        "es": ["piezas de recambio", "piezas de recambio originales"],
        "en": ["spare parts", "original spare parts"],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the multilingual ES/EN lexicon over the canonical operational graph.")
    parser.add_argument("--tbox-file", type=Path, default=OPERATIONAL_TBOX_PATH)
    parser.add_argument("--abox-file", type=Path, default=OPERATIONAL_ABOX_PATH)
    parser.add_argument("--output", type=Path, default=MULTILINGUAL_LEXICON_PATH)
    return parser.parse_args()


def normalize_surface(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9@/_\-.]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_uri(uri: str) -> str:
    return str(uri).split("/")[-1].split("#")[-1]


def humanize_local_name(local_name: str) -> str:
    surface = re.sub(r"(?<!^)([A-Z])", r" \1", local_name or "")
    surface = surface.replace("_", " ")
    surface = re.sub(r"\s+", " ", surface).strip()
    return surface


def guess_english_surface(surface: str) -> str:
    replacements = {
        "manual de la brochadora": "broaching machine manual",
        "brochadora": "broaching machine",
        "maquina": "machine",
        "figura": "figure",
        "directiva": "directive",
        "sistema de seguridad": "safety system",
        "plan de mantenimiento": "maintenance plan",
        "piezas de recambio": "spare parts",
        "departamento de asistencia al cliente": "customer support department",
        "elemento de seguridad": "safety element",
    }
    translated = surface
    for source, target in replacements.items():
        translated = re.sub(source, target, translated, flags=re.IGNORECASE)
    return translated


def load_graphs(tbox_path: Path, abox_path: Path) -> Graph:
    graph = Graph()
    graph.parse(tbox_path, format="turtle")
    graph.parse(abox_path, format="turtle")
    return graph


def load_terms_cache() -> list[dict[str, Any]]:
    if not CACHE_PATH.exists():
        return []
    payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    terms = payload.get("terms", []) if isinstance(payload, dict) else []
    return [term for term in terms if isinstance(term, dict)]


def build_term_alias_index(terms: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for term in terms:
        uri = term.get("uri")
        if not isinstance(uri, str):
            continue
        for surface in [term.get("termino"), term.get("surface_es"), term.get("surface_en"), *(term.get("aliases") or [])]:
            if not isinstance(surface, str):
                continue
            key = normalize_surface(surface)
            if key:
                index[key].append(term)
    return dict(index)


def collect_uri_entries(graph: Graph) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for subject in set(graph.subjects()):
        if not isinstance(subject, URIRef):
            continue
        uri = str(subject)
        if uri not in entries:
            entries[uri] = {
                "canonical_uri": uri,
                "entity_type": "",
                "source_languages": set(),
                "surfaces": {"es": [], "en": []},
                "aliases": [],
                "technical_identifiers": [],
                "document_variants": [],
            }
        entry = entries[uri]
        for _, predicate, obj in graph.triples((subject, None, None)):
            predicate_local = normalize_uri(predicate)
            if predicate == RDF.type and isinstance(obj, URIRef) and not entry["entity_type"]:
                entry["entity_type"] = normalize_uri(obj)
            if predicate_local == "identificador" and isinstance(obj, Literal):
                identifier = str(obj).strip()
                if identifier and identifier not in entry["technical_identifiers"]:
                    entry["technical_identifiers"].append(identifier)
            if predicate_local == "textoExtracto" and isinstance(obj, Literal):
                excerpt = str(obj).strip()
                if excerpt and excerpt not in entry["document_variants"]:
                    entry["document_variants"].append(excerpt[:160])
            if predicate == RDFS.label and isinstance(obj, Literal):
                value = str(obj).strip()
                if not value:
                    continue
                lang = (obj.language or "").lower()
                if lang == "en":
                    if value not in entry["surfaces"]["en"]:
                        entry["surfaces"]["en"].append(value)
                    entry["source_languages"].add("en")
                else:
                    if value not in entry["surfaces"]["es"]:
                        entry["surfaces"]["es"].append(value)
                    entry["source_languages"].add(lang or "es")
        local_name = humanize_local_name(normalize_uri(uri))
        if local_name and local_name not in entry["surfaces"]["es"]:
            entry["surfaces"]["es"].append(local_name)
        if local_name:
            english_guess = guess_english_surface(local_name)
            if english_guess not in entry["surfaces"]["en"]:
                entry["surfaces"]["en"].append(english_guess)
    return entries


def enrich_entries(entries: dict[str, dict[str, Any]], graph: Graph, terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    term_index = build_term_alias_index(terms)
    enriched: list[dict[str, Any]] = []
    for uri, entry in sorted(entries.items()):
        curated = CURATED_ENTITY_SURFACES.get(uri, {})
        for language in ("es", "en"):
            for surface in curated.get(language, []):
                if surface not in entry["surfaces"][language]:
                    entry["surfaces"][language].insert(0, surface)

        for identifier in entry["technical_identifiers"]:
            if identifier not in entry["aliases"]:
                entry["aliases"].append(identifier)
            key = normalize_surface(identifier)
            for term in term_index.get(key, []):
                for alias in term.get("aliases", []):
                    if alias not in entry["aliases"]:
                        entry["aliases"].append(alias)
                for language in ("es", "en"):
                    surface = term.get(f"surface_{language}")
                    if isinstance(surface, str) and surface.strip():
                        if surface not in entry["surfaces"][language]:
                            entry["surfaces"][language].append(surface)

        source_languages = sorted(language for language in entry["source_languages"] if language in {"es", "en"})
        if not source_languages:
            source_languages = ["es"]
        entry["source_languages"] = source_languages
        entry["aliases"] = list(dict.fromkeys(entry["aliases"] + entry["surfaces"]["es"] + entry["surfaces"]["en"]))
        if not entry["entity_type"]:
            entry["entity_type"] = "Entity"
        enriched.append(entry)
    return enriched


def build_surface_index(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = defaultdict(list)
    for entry in entries:
        uri = entry["canonical_uri"]
        entity_type = entry["entity_type"]
        for language in ("es", "en"):
            for surface in entry["surfaces"][language]:
                key = normalize_surface(surface)
                if not key:
                    continue
                payload = {
                    "canonical_uri": uri,
                    "entity_type": entity_type,
                    "language": language,
                    "surface": surface,
                }
                if payload not in index[key]:
                    index[key].append(payload)
        for alias in entry["aliases"]:
            key = normalize_surface(alias)
            if not key:
                continue
            payload = {
                "canonical_uri": uri,
                "entity_type": entity_type,
                "language": "alias",
                "surface": alias,
            }
            if payload not in index[key]:
                index[key].append(payload)
    return dict(index)


def build_payload(tbox_path: Path, abox_path: Path) -> dict[str, Any]:
    graph = load_graphs(tbox_path, abox_path)
    terms = load_terms_cache()
    raw_entries = collect_uri_entries(graph)
    entries = enrich_entries(raw_entries, graph, terms)
    return {
        "metadata": {
            "tbox_path": str(tbox_path),
            "abox_path": str(abox_path),
            "entry_count": len(entries),
            "graph_is_canonical_singleton": True,
            "text_extract_preserves_original_language": True,
        },
        "entries": entries,
        "surface_index": build_surface_index(entries),
    }


def main() -> None:
    args = parse_args()
    payload = build_payload(args.tbox_file, args.abox_file)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Multilingual lexicon built with {payload['metadata']['entry_count']} entries at {args.output}")


if __name__ == "__main__":
    main()
