"""
prompt_assembler.py
Generador dinámico de prompts estructurados para extracción T-Box.
Cruza el texto del manual (density_report.json) con las URIs ontológicas (terms_cache.json).
"""

import json
from pathlib import Path

# Configuración de rutas
DENSITY_REPORT_PATH = Path("data/raw/density_report.json")
TERMS_CACHE_PATH = Path("cache/terms_cache.json")
OUTPUT_PROMPTS_PATH = Path("data/processed/tbox_prompts.json")

def load_json_data(filepath: Path) -> list | dict:
    if not filepath.exists():
        raise FileNotFoundError(f"Archivo requerido no encontrado: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def crear_diccionario_uris(terms_cache: list[dict]) -> dict:
    """Convierte la lista del caché en un diccionario {termino: uri} para búsqueda rápida."""
    return {item["termino"]: item["uri"] for item in terms_cache}

def ensamblar_prompts(chunks_report: list[dict], dict_uris: dict) -> list[dict]:
    prompts_generados = []
    
    prompt_base = """Actúa como un ingeniero de conocimiento experto en web semántica. Genera un modelo conceptual T-Box en formato TTL basado en el texto proporcionado.

Reglas arquitectónicas críticas:
1. CERO instanciamientos: No generes individuos A-Box. Limítate a owl:Class, owl:ObjectProperty y owl:DatatypeProperty.
2. Vocabulario Controlado: Si el texto contiene conceptos de la lista 'Vocabulario Restringido', debes declararlos como clases (owl:Class) usando exactamente el nombre indicado.
3. Trazabilidad: Para cada clase del vocabulario restringido, incluye una propiedad rdfs:isDefinedBy apuntando a su URI origen.

Vocabulario Restringido (Término | URI Origen):
{vocabulario_dinamico}

Texto fuente a modelar:
{texto_chunk}
"""

    for chunk in chunks_report:
        # Ignorar chunks vacíos o con texto irrelevante
        if not chunk["texto"] or len(chunk["texto"]) < 50:
            continue
            
        terminos_encontrados = chunk.get("terms_found", [])
        texto = chunk["texto"]
        
        # Construir el bloque de vocabulario para este chunk específico
        if not terminos_encontrados:
            vocabulario_str = "No se requiere vocabulario controlado para este fragmento."
        else:
            lineas_vocab = []
            for term in terminos_encontrados:
                uri = dict_uris.get(term, "URI_DESCONOCIDA")
                lineas_vocab.append(f"- {term} | {uri}")
            vocabulario_str = "\n".join(lineas_vocab)
            
        # Interpolar el prompt
        prompt_final = prompt_base.format(
            vocabulario_dinamico=vocabulario_str,
            texto_chunk=texto
        )
        
        prompts_generados.append({
            "chunk_id": chunk["chunk_id"],
            "seccion": chunk["seccion"],
            "density_level": chunk["density_level"],
            "prompt": prompt_final
        })
        
    return prompts_generados

def save_prompts(prompts: list[dict], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    print(f"✅ {len(prompts)} prompts dinámicos ensamblados y guardados en {output_path}")

if __name__ == "__main__":
    report_data = load_json_data(DENSITY_REPORT_PATH)
    cache_data = load_json_data(TERMS_CACHE_PATH)
    
    # Extraer el array de términos dependiendo de la estructura exacta de cache_data
    terms_list = cache_data if isinstance(cache_data, list) else cache_data.get("terms", [])
    
    diccionario_semantico = crear_diccionario_uris(terms_list)
    prompts_listos = ensamblar_prompts(report_data, diccionario_semantico)
    
    save_prompts(prompts_listos, OUTPUT_PROMPTS_PATH)