"""
prompt_assembler.py
Generador dinámico de prompts estructurados (CoT) para extracción atómica T-Box.
Integra metadatos de sección, reglas de normalización y vocabularios ontológicos.
"""

import json
from pathlib import Path

DENSITY_REPORT_PATH = Path("data/raw/density_report.json")
TERMS_CACHE_PATH = Path("cache/terms_cache.json")
OUTPUT_PROMPTS_PATH = Path("data/processed/tbox_prompts.json")

def load_json_data(filepath: Path) -> list | dict:
    if not filepath.exists():
        raise FileNotFoundError(f"Archivo requerido no encontrado: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def crear_diccionario_uris(terms_cache: list[dict]) -> dict:
    return {item["termino"]: item["uri"] for item in terms_cache}

def ensamblar_prompts(chunks_report: list[dict], dict_uris: dict) -> list[dict]:
    prompts_generados = []
    
    prompt_base = """Actúa como un ingeniero de conocimiento experto en web semántica. Genera un modelo conceptual T-Box en formato Turtle (TTL) extrayendo el conocimiento de este fragmento de manual técnico. Aplica razonamiento paso a paso (Chain of Thought) internamente, pero tu ÚNICA salida debe ser el código TTL válido, sin texto conversacional.

CONTEXTO DEL FRAGMENTO (Usa esto para situar el texto y resolver anáforas):
- Páginas: {paginas}
- Sección: {seccion}
- Título: {titulo}

REGLAS ARQUITECTÓNICAS Y NORMALIZACIÓN:
1. Cero Instanciamientos: Genera exclusivamente owl:Class, owl:ObjectProperty y owl:DatatypeProperty. Prohibido crear individuos (A-Box).
2. Namespaces Dinámicos: Define y utiliza prefijos lógicos según el dominio (ej. @prefix mecanica: <...>, @prefix elec: <...>, @prefix base: <...>).
3. Nomenclatura Estricta: Usa PascalCase para Clases (ej. base:BombaHidraulica) y camelCase para Propiedades (ej. mecanica:estaConectadoA).
4. Resolución de Anáforas: Si el texto menciona "el componente" o "el sistema", asócialo explícitamente a la entidad descrita en el Título o Sección.
5. Anti-Alucinación (Flags de Incompletitud): Si identificas una relación válida pero la entidad destino no está claramente definida en el texto, genérala y añade la anotación `rdfs:comment "Incompleto: Requiere resolución externa"`.
6. Vocabulario Controlado: Si el texto contiene los conceptos listados abajo, decláralos como owl:Class (ajustando a PascalCase) y añade exactamente la URI origen usando rdfs:isDefinedBy.

VOCABULARIO RESTRINGIDO (Término detectado | URI Origen):
{vocabulario_dinamico}

TEXTO FUENTE A MODELAR:
{texto_chunk}
"""

    for chunk in chunks_report:
        texto = chunk.get("texto", "")
        if not texto or len(texto) < 50:
            continue
            
        terminos_encontrados = chunk.get("terms_found", [])
        
        if not terminos_encontrados:
            vocabulario_str = "No se requiere vocabulario controlado para este fragmento."
        else:
            lineas_vocab = []
            for term in terminos_encontrados:
                uri = dict_uris.get(term, "URI_DESCONOCIDA")
                lineas_vocab.append(f"- {term} | {uri}")
            vocabulario_str = "\n".join(lineas_vocab)
            
        prompt_final = prompt_base.format(
            paginas=chunk.get("paginas", "N/A"),
            seccion=chunk.get("seccion", "N/A"),
            titulo=chunk.get("titulo", "N/A"),
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
    
    terms_list = cache_data if isinstance(cache_data, list) else cache_data.get("terms", [])
    
    diccionario_semantico = crear_diccionario_uris(terms_list)
    prompts_listos = ensamblar_prompts(report_data, diccionario_semantico)
    
    save_prompts(prompts_listos, OUTPUT_PROMPTS_PATH)