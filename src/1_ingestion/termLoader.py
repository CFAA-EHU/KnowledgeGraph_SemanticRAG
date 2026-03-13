# -*- coding: utf-8 -*-
import sys
import io
import json
import time
import argparse
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

import requests
import spacy
from SPARQLWrapper import SPARQLWrapper, JSON as SPARQL_JSON

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CACHE_PATH = Path("cache/terms_cache.json")
CACHE_TTL_DAYS = 30
SPARQL_TIMEOUT = 15
ESDBPEDIA_ENDPOINT = "https://es.dbpedia.org/sparql"

AAS_CONCEPT_DESCRIPTIONS = [
    "MaxRotationSpeed", "NominalVoltage", "NominalCurrent", "NominalPower",
    "NominalFrequency", "NominalTorque", "Weight", "Dimensions",
    "OperatingTemperatureRange", "StorageTemperatureRange",
    "MaintenanceInterval", "LubricationInterval", "InspectionInterval",
    "ReplacementInterval", "ServiceLife", "MaintenanceProcedure",
    "Actuator", "Sensor", "Controller", "Drive", "Motor", "Pump",
    "Valve", "Cylinder", "Bearing", "Gear", "Coupling", "Brake",
    "Filter", "HeatExchanger", "Conveyor", "Gripper", "Clamp",
]

HELSINKI_MODEL = "Helsinki-NLP/opus-mt-en-es"
TOP_N_CATEGORIES = 7

def parsear_texto_crudo(filepath: str) -> list[str]:
    path = Path(filepath)
    if not path.exists():
        print(f"Error: Archivo no encontrado en {filepath}")
        sys.exit(1)
    
    content = path.read_text(encoding="utf-8")
    header_pattern = re.compile(
        r"---\s*Páginas:\s*\[.*?\]\s*\|\s*Sección:\s*.*?\s*\|\s*Título:\s*.*?\s*---"
    )
    parts = header_pattern.split(content)
    return [p.strip() for p in parts if p.strip()]

def descubrir_categorias_dinamicas(filepath: str) -> list[str]:
    print("[Discovery] Analizando el texto para descubrir categorías en ESDBpedia...")
    textos = parsear_texto_crudo(filepath)
    
    try:
        nlp = spacy.load("es_core_news_sm")
    except OSError:
        print("Error crítico: Modelo es_core_news_sm no encontrado.")
        sys.exit(1)

    doc = nlp(" ".join(textos))
    sustantivos = [token.lemma_.lower() for token in doc if token.pos_ == "NOUN" and len(token.lemma_) > 3]
    
    conteo = Counter(sustantivos)
    terminos_frecuentes = [term for term, freq in conteo.most_common(100) if freq >= 2]
    
    sparql = SPARQLWrapper(ESDBPEDIA_ENDPOINT)
    sparql.setReturnFormat(SPARQL_JSON)
    categorias_encontradas = []
    
    lote_size = 20
    for i in range(0, len(terminos_frecuentes), lote_size):
        lote = terminos_frecuentes[i:i + lote_size]
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
            for r in resultados["results"]["bindings"]:
                uri_categoria = r["category"]["value"]
                if "http://es.dbpedia.org/resource/" in uri_categoria:
                    nombre_cat = uri_categoria.replace("http://es.dbpedia.org/resource/", "")
                    categorias_encontradas.append(nombre_cat)
        except Exception as e:
            print(f"  [WARN] Fallo en lote de descubrimiento SPARQL: {e}")
        time.sleep(0.5)

    conteo_categorias = Counter(categorias_encontradas)
    top_categorias = [cat for cat, freq in conteo_categorias.most_common(TOP_N_CATEGORIES)]
    print(f"  [OK] Categorías descubiertas: {top_categorias}")
    return top_categorias

def fetch_esdbpedia_terms(categorias: list[str]) -> list[dict]:
    print("[ESDBpedia] Extrayendo términos técnicos de las categorías descubiertas...")
    terms_dict = {}
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
            for r in results["results"]["bindings"]:
                label = r["label"]["value"].strip().lower()
                uri = r["concept"]["value"]
                
                if len(label.split()) <= 4 and label not in terms_dict:
                    terms_dict[label] = {"termino": label, "uri": uri}
            print(f"  [OK] {category}: {len(results['results']['bindings'])} términos procesados")
        except Exception as e:
            print(f"  [WARN] {category}: error — {e}")
        time.sleep(0.5)

    return list(terms_dict.values())

def translate_terms_helsinki(terms_en: list[str]) -> list[dict]:
    print(f"[Traduccion] Traduciendo {len(terms_en)} términos AAS con Helsinki-NLP...")
    translated_terms = []

    try:
        from transformers import pipeline
        translator = pipeline("translation", model=HELSINKI_MODEL)
        for term in terms_en:
            result = translator(term)
            translated_text = result[0]["translation_text"].strip().lower()
            uri = f"https://admin-shell.io/dictionary/{term}"
            
            if translated_text and len(translated_text.split()) <= 5:
                translated_terms.append({"termino": translated_text, "uri": uri})
        print("  [OK] Traduccion local completada")

    except Exception as e:
        print(f"  [INFO] Pipeline local no disponible ({e}), usando HuggingFace API...")
        api_url = f"https://api-inference.huggingface.co/models/{HELSINKI_MODEL}"
        headers = {"Content-Type": "application/json"}
        batch_size = 20
        
        for i in range(0, len(terms_en), batch_size):
            batch = terms_en[i:i + batch_size]
            payload = {"inputs": batch}
            try:
                resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    results = resp.json()
                    for idx, r in enumerate(results):
                        original_term = batch[idx]
                        uri = f"https://admin-shell.io/dictionary/{original_term}"
                        
                        if isinstance(r, list):
                            t_text = r[0]["translation_text"].strip().lower()
                        else:
                            t_text = r.get("translation_text", "").strip().lower()
                            
                        if t_text and len(t_text.split()) <= 5:
                            translated_terms.append({"termino": t_text, "uri": uri})
                else:
                    for t in batch:
                        translated_terms.append({"termino": t.lower(), "uri": f"https://admin-shell.io/dictionary/{t}"})
            except Exception:
                for t in batch:
                    translated_terms.append({"termino": t.lower(), "uri": f"https://admin-shell.io/dictionary/{t}"})
            time.sleep(1)

    return translated_terms

def fetch_aas_terms() -> list[dict]:
    print("[AAS] Procesando términos AAS / ECLASS...")
    return translate_terms_helsinki(AAS_CONCEPT_DESCRIPTIONS)

def load_cache() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        cache = json.load(f)

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
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def get_terms(filepath: str = None, force_refresh: bool = False) -> list[dict]:
    if not force_refresh:
        cache = load_cache()
        if cache:
            return cache["terms"]

    if not filepath:
        print("Error crítico: Para forzar un refresh dinámico debes proporcionar la ruta del archivo de texto (--input).")
        sys.exit(1)

    categorias_dinamicas = descubrir_categorias_dinamicas(filepath)
    esdbpedia_terms = fetch_esdbpedia_terms(categorias_dinamicas)
    aas_terms = fetch_aas_terms()

    merged_dict = {t["termino"]: t for t in esdbpedia_terms + aas_terms}
    all_terms = list(merged_dict.values())
    all_terms.sort(key=lambda x: x["termino"])

    sources = {
        "esdbpedia": {
            "endpoint": ESDBPEDIA_ENDPOINT,
            "dynamic_categories": categorias_dinamicas,
            "terms_count": len(esdbpedia_terms),
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
    parser.add_argument("--input", type=str, required=True, help="Ruta al archivo de chunks para descubrir categorías")
    args = parser.parse_args()

    terms = get_terms(filepath=args.input, force_refresh=args.refresh)
    for t in terms[:10]:
        print(f"  - {t['termino']} ({t['uri']})")