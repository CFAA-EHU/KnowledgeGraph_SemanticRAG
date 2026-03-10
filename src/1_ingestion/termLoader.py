# -*- coding: utf-8 -*-
import sys
import io
# Forzar UTF-8 en la terminal de Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

"""
term_loader.py
Issue #1 — Carga y cacheo de términos técnicos desde ontologías externas.

Fuentes:
  1. ESDBpedia   → términos en español vía SPARQL
  2. AAS / ECLASS → términos industriales en inglés, traducidos con Helsinki-NLP

Flujo:
  - Si existe cache/terms_cache.json y no ha expirado → lo usa directamente
  - Si no → consulta las ontologías, traduce, fusiona y guarda el cache

Uso standalone:
    python src/1_ingestion/term_loader.py --refresh
"""

import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta

import requests
from SPARQLWrapper import SPARQLWrapper, JSON as SPARQL_JSON


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

CACHE_PATH        = Path("cache/terms_cache.json")
CACHE_TTL_DAYS    = 30          # Renovar el cache cada 30 días
SPARQL_TIMEOUT    = 15          # segundos

ESDBPEDIA_ENDPOINT = "https://es.dbpedia.org/sparql"

# Categorías de ESDBpedia relevantes para maquinaria industrial
ESDBPEDIA_CATEGORIES = [
    "Categoría:Máquinas",
    "Categoría:Ingeniería_mecánica",
    "Categoría:Hidráulica",
    "Categoría:Neumática",
    "Categoría:Manufactura",
    "Categoría:Herramientas",
    "Categoría:Metrología",
]

# Submodelos AAS relevantes para maquinaria
# Fuente: IDTA / admin-shell.io
AAS_CONCEPT_DESCRIPTIONS = [
    # TechnicalData submodel elements
    "MaxRotationSpeed", "NominalVoltage", "NominalCurrent", "NominalPower",
    "NominalFrequency", "NominalTorque", "Weight", "Dimensions",
    "OperatingTemperatureRange", "StorageTemperatureRange",
    # Maintenance submodel elements
    "MaintenanceInterval", "LubricationInterval", "InspectionInterval",
    "ReplacementInterval", "ServiceLife", "MaintenanceProcedure",
    # Componentes comunes en AAS
    "Actuator", "Sensor", "Controller", "Drive", "Motor", "Pump",
    "Valve", "Cylinder", "Bearing", "Gear", "Coupling", "Brake",
    "Filter", "HeatExchanger", "Conveyor", "Gripper", "Clamp",
]

# Modelo Helsinki-NLP para traducción EN → ES
HELSINKI_MODEL = "Helsinki-NLP/opus-mt-en-es"


# ─────────────────────────────────────────────────────────────────────────────
# 1. ESDBPEDIA
# ─────────────────────────────────────────────────────────────────────────────

def fetch_esdbpedia_terms() -> list[str]:
    """
    Consulta ESDBpedia para obtener etiquetas en español de conceptos
    relacionados con maquinaria industrial.
    """
    print("[ESDBpedia] Consultando ESDBpedia...")
    terms = set()
    sparql = SPARQLWrapper(ESDBPEDIA_ENDPOINT)
    sparql.setTimeout(SPARQL_TIMEOUT)
    sparql.setReturnFormat(SPARQL_JSON)

    for category in ESDBPEDIA_CATEGORIES:
        # Usar URI completa para evitar error de sintaxis SPARQL con el ":" de "Categoría:X"
        category_uri = f"http://es.dbpedia.org/resource/{category}"
        query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX dct:  <http://purl.org/dc/terms/>

        SELECT DISTINCT ?label WHERE {{
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
            for r in results["results"]["bindings"]:
                label = r["label"]["value"].strip().lower()
                # Filtrar etiquetas muy largas (probablemente frases, no términos)
                if len(label.split()) <= 4:
                    terms.add(label)
            print(f"  [OK] {category}: {len(results['results']['bindings'])} términos")
        except Exception as e:
            print(f"  [WARN] {category}: error — {e}")
        time.sleep(0.5)  # Respetar rate limit

    print(f"  → Total ESDBpedia: {len(terms)} términos únicos en español")
    return sorted(terms)


# ─────────────────────────────────────────────────────────────────────────────
# 2. AAS + TRADUCCIÓN
# ─────────────────────────────────────────────────────────────────────────────

def translate_terms_helsinki(terms_en: list[str]) -> list[str]:
    """
    Traduce una lista de términos del inglés al español usando
    Helsinki-NLP/opus-mt-en-es vía HuggingFace Inference API.

    Si el modelo no está disponible localmente, usa la API de HuggingFace.
    """
    print(f"[Traduccion] Traduciendo {len(terms_en)} términos AAS con Helsinki-NLP...")
    translated = []

    try:
        # Intentar primero con pipeline local
        # NOTA: en versiones nuevas de transformers usar "translation" en vez de "translation_en_to_es"
        from transformers import pipeline
        translator = pipeline("translation", model=HELSINKI_MODEL)
        for term in terms_en:
            result = translator(term)
            translated_text = result[0]["translation_text"].strip().lower()
            translated.append(translated_text)
        print(f"  [OK] Traduccion local completada")

    except (ImportError, KeyError, Exception) as e:
        # Fallback: HuggingFace Inference API (no requiere instalación)
        print(f"  [INFO] Pipeline local no disponible ({e}), usando HuggingFace Inference API...")
        api_url = f"https://api-inference.huggingface.co/models/{HELSINKI_MODEL}"
        headers = {"Content-Type": "application/json"}

        # Procesar en lotes de 20 para no saturar la API
        batch_size = 20
        for i in range(0, len(terms_en), batch_size):
            batch = terms_en[i:i + batch_size]
            payload = {"inputs": batch}
            try:
                resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    results = resp.json()
                    for r in results:
                        if isinstance(r, list):
                            translated.append(r[0]["translation_text"].lower())
                        else:
                            translated.append(r.get("translation_text", "").lower())
                else:
                    print(f"  [WARN] API error {resp.status_code}, usando términos en inglés como fallback")
                    translated.extend([t.lower() for t in batch])
            except Exception as e:
                print(f"  [WARN] Error en traducción: {e}, usando inglés como fallback")
                translated.extend([t.lower() for t in batch])
            time.sleep(1)

    # Limpiar: eliminar términos vacíos o demasiado largos
    translated_clean = [
        t.strip() for t in translated
        if t.strip() and len(t.split()) <= 5
    ]
    print(f"  → Total AAS traducidos: {len(translated_clean)} términos en español")
    return translated_clean


def fetch_aas_terms() -> list[str]:
    """
    Devuelve los términos AAS definidos en TECHNICAL_TERMS
    y los traduce al español con Helsinki-NLP.
    """
    print("[AAS] Procesando términos AAS / ECLASS...")
    return translate_terms_helsinki(AAS_CONCEPT_DESCRIPTIONS)


# ─────────────────────────────────────────────────────────────────────────────
# 3. CACHE
# ─────────────────────────────────────────────────────────────────────────────

def load_cache() -> dict | None:
    """
    Carga el cache si existe y no ha expirado.
    Devuelve None si no existe o está expirado.
    """
    if not CACHE_PATH.exists():
        return None

    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        cache = json.load(f)

    generated_at = datetime.fromisoformat(cache.get("generated_at", "2000-01-01"))
    if datetime.now() - generated_at > timedelta(days=CACHE_TTL_DAYS):
        print(f"[INFO] Cache expirado (generado el {generated_at.date()}), renovando...")
        return None

    print(f"[OK] Cache cargado desde {CACHE_PATH} (generado el {generated_at.date()})")
    return cache


def save_cache(terms: list[str], sources: dict):
    """Guarda los términos en el archivo de cache JSON."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache = {
        "generated_at": datetime.now().isoformat(),
        "ttl_days":     CACHE_TTL_DAYS,
        "total_terms":  len(terms),
        "sources":      sources,
        "terms":        terms,
    }
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"[Guardado] Cache guardado en {CACHE_PATH} ({len(terms)} términos)")


# ─────────────────────────────────────────────────────────────────────────────
# 4. PUNTO DE ENTRADA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def get_terms(force_refresh: bool = False) -> list[str]:
    """
    Devuelve la lista consolidada de términos técnicos en español.

    Flujo:
      1. Si hay cache válido y no se fuerza refresh → devuelve el cache
      2. Si no → consulta ESDBpedia + AAS, traduce, fusiona y cachea
    """
    if not force_refresh:
        cache = load_cache()
        if cache:
            return cache["terms"]

    print("\n[Cargando] Construyendo lista de términos técnicos desde ontologías...\n")

    # Obtener términos de cada fuente
    esdbpedia_terms = fetch_esdbpedia_terms()
    aas_terms       = fetch_aas_terms()

    # Fusionar y deduplicar
    all_terms = sorted(set(esdbpedia_terms + aas_terms))

    sources = {
        "esdbpedia": {
            "endpoint":    ESDBPEDIA_ENDPOINT,
            "categories":  ESDBPEDIA_CATEGORIES,
            "terms_count": len(esdbpedia_terms),
        },
        "aas": {
            "concepts":          AAS_CONCEPT_DESCRIPTIONS,
            "translation_model": HELSINKI_MODEL,
            "terms_count":       len(aas_terms),
        },
    }

    save_cache(all_terms, sources)
    print(f"\n[OK] Total términos consolidados: {len(all_terms)}\n")
    return all_terms


# ─────────────────────────────────────────────────────────────────────────────
# MAIN (uso standalone para regenerar el cache)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga y cachea términos técnicos desde ontologías")
    parser.add_argument("--refresh", action="store_true", help="Forzar regeneración del cache")
    args = parser.parse_args()

    terms = get_terms(force_refresh=args.refresh)

    print(f"\n[Lista] Primeros 30 términos cargados:")
    for t in terms[:30]:
        print(f"  - {t}")
    print(f"  ... y {max(0, len(terms) - 30)} más")