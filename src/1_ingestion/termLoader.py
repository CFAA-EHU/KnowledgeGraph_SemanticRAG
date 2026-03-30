# -*- coding: utf-8 -*-
import argparse
import io
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
import spacy
from SPARQLWrapper import JSON as SPARQL_JSON
from SPARQLWrapper import SPARQLWrapper

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CACHE_PATH = Path("cache/terms_cache.json")
CACHE_TTL_DAYS = 30
SPARQL_TIMEOUT = 15
ESDBPEDIA_ENDPOINT = "https://es.dbpedia.org/sparql"

AAS_CONCEPT_DESCRIPTIONS = [
    "MaxRotationSpeed",
    "NominalVoltage",
    "NominalCurrent",
    "NominalPower",
    "NominalFrequency",
    "NominalTorque",
    "Weight",
    "Dimensions",
    "OperatingTemperatureRange",
    "StorageTemperatureRange",
    "MaintenanceInterval",
    "LubricationInterval",
    "InspectionInterval",
    "ReplacementInterval",
    "ServiceLife",
    "MaintenanceProcedure",
    "Actuator",
    "Sensor",
    "Controller",
    "Drive",
    "Motor",
    "Pump",
    "Valve",
    "Cylinder",
    "Bearing",
    "Gear",
    "Coupling",
    "Brake",
    "Filter",
    "HeatExchanger",
    "Conveyor",
    "Gripper",
    "Clamp",
]

HELSINKI_MODEL = "Helsinki-NLP/opus-mt-en-es"
TOP_N_CATEGORIES = 7
TOP_LOCAL_TERMS = 80
HEADER_PATTERN = re.compile(
    r"---\s*P[áa]ginas:\s*\[.*?\]\s*\|\s*Secci[óo]n:\s*.*?\s*\|\s*T[íi]tulo:\s*.*?\s*---",
    flags=re.IGNORECASE,
)


def enrich_term_entry(entry: dict[str, Any]) -> dict[str, Any]:
    termino = (entry.get("termino") or "").strip().lower()
    surface_es = (entry.get("surface_es") or termino).strip().lower()
    surface_en = (entry.get("surface_en") or "").strip().lower()
    source_language = entry.get("source_language")
    aliases = entry.get("aliases")
    if not isinstance(aliases, list):
        aliases = []
    enriched_aliases: list[str] = []
    for alias in [termino, surface_es, surface_en, *aliases]:
        if isinstance(alias, str):
            normalized = alias.strip().lower()
            if normalized and normalized not in enriched_aliases:
                enriched_aliases.append(normalized)
    enriched = {
        "termino": termino,
        "uri": entry.get("uri", ""),
        "source_language": source_language or ("en" if surface_en and surface_en != termino else "es"),
        "surface_es": surface_es or termino,
        "surface_en": surface_en,
        "aliases": enriched_aliases,
    }
    for key, value in entry.items():
        if key not in enriched:
            enriched[key] = value
    return enriched


def enrich_term_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [enrich_term_entry(entry) for entry in entries]


def _read_text_with_fallback(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("termLoader", b"", 0, 1, f"No se pudo decodificar {path}")


def _normalize_input_paths(filepath: str | None = None, filepaths: list[str] | None = None) -> list[Path]:
    raw_paths: list[str] = []
    if filepath:
        raw_paths.append(filepath)
    if filepaths:
        raw_paths.extend(filepaths)

    normalized_paths: list[Path] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        path = Path(raw_path)
        if not path.exists():
            print(f"Error: Archivo no encontrado en {raw_path}")
            sys.exit(1)
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        normalized_paths.append(path)

    if not normalized_paths:
        print("Error crítico: Debes proporcionar al menos un archivo de entrada.")
        sys.exit(1)

    return normalized_paths


def parsear_texto_crudo(filepath: str | None = None, filepaths: list[str] | None = None) -> list[str]:
    paths = _normalize_input_paths(filepath=filepath, filepaths=filepaths)
    parts: list[str] = []
    for path in paths:
        content = _read_text_with_fallback(path)
        parts.extend(fragment.strip() for fragment in HEADER_PATTERN.split(content) if fragment.strip())
    return parts


def _extract_candidate_terms(textos: list[str]) -> list[str]:
    try:
        nlp = spacy.load("es_core_news_sm")
    except OSError:
        print("Error crítico: Modelo es_core_news_sm no encontrado.")
        sys.exit(1)

    sustantivos: list[str] = []
    for doc in nlp.pipe(textos, batch_size=8):
        sustantivos.extend(token.lemma_.lower() for token in doc if token.pos_ == "NOUN" and len(token.lemma_) > 3)

    conteo = Counter(sustantivos)
    return [term for term, freq in conteo.most_common(100) if freq >= 2]


def descubrir_categorias_dinamicas(
    filepath: str | None = None,
    filepaths: list[str] | None = None,
) -> list[str]:
    print("[Discovery] Analizando el texto para descubrir categorías en ESDBpedia...")
    textos = parsear_texto_crudo(filepath=filepath, filepaths=filepaths)
    terminos_frecuentes = _extract_candidate_terms(textos)

    sparql = SPARQLWrapper(ESDBPEDIA_ENDPOINT)
    sparql.setReturnFormat(SPARQL_JSON)
    categorias_encontradas: list[str] = []

    lote_size = 20
    for i in range(0, len(terminos_frecuentes), lote_size):
        lote = terminos_frecuentes[i : i + lote_size]
        valores_sparql = " ".join([f'"{term}"@es' for term in lote])

        query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX dct:  <http://purl.org/dc/terms/>
        SELECT ?category WHERE {{
          VALUES ?label {{ {valores_sparql} }}
          ?concept rdfs:label ?label ;
                   dct:subject ?category .
        }}
        """
        sparql.setQuery(query)
        try:
            resultados = sparql.query().convert()
            for result in resultados["results"]["bindings"]:
                uri_categoria = result["category"]["value"]
                if "http://es.dbpedia.org/resource/" in uri_categoria:
                    nombre_categoria = uri_categoria.replace("http://es.dbpedia.org/resource/", "")
                    categorias_encontradas.append(nombre_categoria)
        except Exception as exc:
            print(f"  [WARN] Fallo en lote de descubrimiento SPARQL: {exc}")
        time.sleep(0.5)

    conteo_categorias = Counter(categorias_encontradas)
    top_categorias = [categoria for categoria, _freq in conteo_categorias.most_common(TOP_N_CATEGORIES)]
    print(f"  [OK] Categorías descubiertas: {top_categorias}")
    return top_categorias


def fetch_local_corpus_terms(
    filepath: str | None = None,
    filepaths: list[str] | None = None,
) -> list[dict[str, Any]]:
    print("[Corpus] Extrayendo términos frecuentes directamente del corpus integrado...")
    textos = parsear_texto_crudo(filepath=filepath, filepaths=filepaths)
    local_terms = _extract_candidate_terms(textos)[:TOP_LOCAL_TERMS]
    return [
        enrich_term_entry(
            {
                "termino": term,
                "uri": f"local://corpus/{term.replace(' ', '_')}",
                "source_language": "es",
                "surface_es": term,
                "aliases": [term],
            }
        )
        for term in local_terms
    ]


def fetch_esdbpedia_terms(categorias: list[str]) -> list[dict]:
    print("[ESDBpedia] Extrayendo términos técnicos de las categorías descubiertas...")
    terms_dict: dict[str, dict[str, Any]] = {}
    sparql = SPARQLWrapper(ESDBPEDIA_ENDPOINT)
    sparql.setTimeout(SPARQL_TIMEOUT)
    sparql.setReturnFormat(SPARQL_JSON)

    for category in categorias:
        category_uri = f"http://es.dbpedia.org/resource/{category}"
        query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX dct:  <http://purl.org/dc/terms/>

        SELECT DISTINCT ?concept ?label WHERE {{
          ?concept dct:subject <{category_uri}> ;
                   rdfs:label ?label .
          FILTER(lang(?label) = "es")
          FILTER(STRLEN(str(?label)) > 3)
        }}
        LIMIT 200
        """
        try:
            sparql.setQuery(query)
            results = sparql.query().convert()
            for result in results["results"]["bindings"]:
                label = result["label"]["value"].strip().lower()
                uri = result["concept"]["value"]

                if len(label.split()) <= 4 and label not in terms_dict:
                    terms_dict[label] = enrich_term_entry(
                        {
                            "termino": label,
                            "uri": uri,
                            "source_language": "es",
                            "surface_es": label,
                            "aliases": [label],
                        }
                    )
            print(f"  [OK] {category}: {len(results['results']['bindings'])} términos procesados")
        except Exception as exc:
            print(f"  [WARN] {category}: error — {exc}")
        time.sleep(0.5)

    return list(terms_dict.values())


def translate_terms_helsinki(terms_en: list[str]) -> list[dict]:
    print(f"[Traducción] Traduciendo {len(terms_en)} términos AAS con Helsinki-NLP...")
    translated_terms: list[dict[str, Any]] = []

    try:
        from transformers import pipeline

        translator = pipeline("translation", model=HELSINKI_MODEL)
        for term in terms_en:
            result = translator(term)
            translated_text = result[0]["translation_text"].strip().lower()
            uri = f"https://admin-shell.io/dictionary/{term}"

            if translated_text and len(translated_text.split()) <= 5:
                translated_terms.append(
                    enrich_term_entry(
                        {
                            "termino": translated_text,
                            "uri": uri,
                            "source_language": "en",
                            "surface_es": translated_text,
                            "surface_en": term.strip().lower(),
                            "aliases": [translated_text, term.strip().lower()],
                        }
                    )
                )
        print("  [OK] Traducción local completada")

    except Exception as exc:
        print(f"  [INFO] Pipeline local no disponible ({exc}), usando HuggingFace API...")
        api_url = f"https://api-inference.huggingface.co/models/{HELSINKI_MODEL}"
        headers = {"Content-Type": "application/json"}
        batch_size = 20

        for i in range(0, len(terms_en), batch_size):
            batch = terms_en[i : i + batch_size]
            payload = {"inputs": batch}
            try:
                resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    results = resp.json()
                    for idx, result in enumerate(results):
                        original_term = batch[idx]
                        uri = f"https://admin-shell.io/dictionary/{original_term}"

                        if isinstance(result, list):
                            translated_text = result[0]["translation_text"].strip().lower()
                        else:
                            translated_text = result.get("translation_text", "").strip().lower()

                        if translated_text and len(translated_text.split()) <= 5:
                            translated_terms.append(
                                enrich_term_entry(
                                    {
                                        "termino": translated_text,
                                        "uri": uri,
                                        "source_language": "en",
                                        "surface_es": translated_text,
                                        "surface_en": original_term.strip().lower(),
                                        "aliases": [translated_text, original_term.strip().lower()],
                                    }
                                )
                            )
                else:
                    for term in batch:
                        translated_terms.append(
                            enrich_term_entry(
                                {
                                    "termino": term.lower(),
                                    "uri": f"https://admin-shell.io/dictionary/{term}",
                                    "source_language": "en",
                                    "surface_es": term.lower(),
                                    "surface_en": term.lower(),
                                    "aliases": [term.lower()],
                                }
                            )
                        )
            except Exception:
                for term in batch:
                    translated_terms.append(
                        enrich_term_entry(
                            {
                                "termino": term.lower(),
                                "uri": f"https://admin-shell.io/dictionary/{term}",
                                "source_language": "en",
                                "surface_es": term.lower(),
                                "surface_en": term.lower(),
                                "aliases": [term.lower()],
                            }
                        )
                    )
            time.sleep(1)

    return translated_terms


def fetch_aas_terms() -> list[dict]:
    print("[AAS] Procesando términos AAS / ECLASS...")
    return translate_terms_helsinki(AAS_CONCEPT_DESCRIPTIONS)


def load_cache() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    with open(CACHE_PATH, "r", encoding="utf-8") as file:
        cache = json.load(file)

    generated_at = datetime.fromisoformat(cache.get("generated_at", "2000-01-01"))
    if datetime.now() - generated_at > timedelta(days=CACHE_TTL_DAYS):
        print(f"[INFO] Cache expirado (generado el {generated_at.date()}), renovando...")
        return None

    return cache


def save_cache(terms: list[dict], sources: dict):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache = {
        "generated_at": datetime.now().isoformat(),
        "ttl_days": CACHE_TTL_DAYS,
        "total_terms": len(terms),
        "sources": sources,
        "terms": terms,
    }
    with open(CACHE_PATH, "w", encoding="utf-8") as file:
        json.dump(cache, file, ensure_ascii=False, indent=2)


def get_terms(
    filepath: str | None = None,
    force_refresh: bool = False,
    filepaths: list[str] | None = None,
) -> list[dict]:
    if not force_refresh:
        cache = load_cache()
        if cache:
            return enrich_term_entries(cache["terms"])

    input_paths = _normalize_input_paths(filepath=filepath, filepaths=filepaths)
    categorias_dinamicas = descubrir_categorias_dinamicas(filepaths=[str(path) for path in input_paths])
    esdbpedia_terms = fetch_esdbpedia_terms(categorias_dinamicas)
    local_corpus_terms = fetch_local_corpus_terms(filepaths=[str(path) for path in input_paths])
    aas_terms = fetch_aas_terms()

    merged_dict = {term["termino"]: term for term in esdbpedia_terms + local_corpus_terms + aas_terms}
    all_terms = enrich_term_entries(list(merged_dict.values()))
    all_terms.sort(key=lambda item: item["termino"])

    sources = {
        "esdbpedia": {
            "endpoint": ESDBPEDIA_ENDPOINT,
            "dynamic_categories": categorias_dinamicas,
            "terms_count": len(esdbpedia_terms),
            "source_files": [str(path).replace("\\", "/") for path in input_paths],
        },
        "local_corpus": {
            "terms_count": len(local_corpus_terms),
        },
        "aas": {
            "translation_model": HELSINKI_MODEL,
            "terms_count": len(aas_terms),
        },
    }

    save_cache(all_terms, sources)
    return all_terms


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--input",
        type=str,
        action="append",
        required=True,
        help="Ruta a un archivo de chunks para descubrir categorías; puede repetirse.",
    )
    args = parser.parse_args()

    terms = get_terms(filepaths=args.input, force_refresh=args.refresh)
    for term in terms[:10]:
        print(f"  - {term['termino']} ({term['uri']})")
