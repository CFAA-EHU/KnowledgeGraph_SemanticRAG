import asyncio
import json
import re
import os
import sys
from pathlib import Path

from mistralai import Mistral
from rdflib import Graph

PROMPTS_PATH = Path("data/processed/tbox_prompts.json")
OUTPUT_DIR = Path("data/processed/graphs/")
MAX_CONCURRENCY = 5
MODEL = "mistral-small-latest"

api_key = os.environ.get("MISTRAL_API_KEY")
if not api_key:
    print("Error: Define la variable de entorno MISTRAL_API_KEY antes de ejecutar.")
    sys.exit(1)

client = Mistral(api_key=api_key)

def aislar_sintaxis_ttl(respuesta_llm: str) -> str:
    # Modificado para evitar que la interfaz de chat corte el código
    patron = r"`{3}(?:turtle|ttl)?\n(.*?)`{3}"
    match = re.search(patron, respuesta_llm, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return respuesta_llm.strip()

def validar_sintaxis_rdf(ttl_data: str) -> bool:
    try:
        g = Graph()
        g.parse(data=ttl_data, format="turtle")
        return True
    except Exception:
        return False

async def procesar_chunk(semaforo: asyncio.Semaphore, chunk_data: dict):
    async with semaforo:
        chunk_id = chunk_data["chunk_id"]
        prompt = chunk_data["prompt"]
        archivo_salida = OUTPUT_DIR / f"chunk_{chunk_id:03d}.ttl"
        
        if archivo_salida.exists():
            return chunk_id, "Omitido"

        try:
            respuesta = await client.chat.complete_async(
                model=MODEL,
                temperature=0.0,
                messages=[
                    {
                        "role": "system", 
                        "content": "Eres un motor de serialización RDF. Responde exclusivamente con sintaxis Turtle (TTL) válida. Omite explicaciones o texto conversacional. Genera modelo T-Box, prohíbe individuos A-Box."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ]
            )
            
            ttl_puro = aislar_sintaxis_ttl(respuesta.choices[0].message.content)
            
            if not validar_sintaxis_rdf(ttl_puro):
                return chunk_id, "Error: Sintaxis TTL inválida"
            
            with open(archivo_salida, "w", encoding="utf-8") as f:
                f.write(ttl_puro)
                
            return chunk_id, "OK"
            
        except Exception as e:
            return chunk_id, f"Error: {str(e)}"

async def orquestar_extraccion():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    if not PROMPTS_PATH.exists():
        print(f"Error: Archivo de prompts no encontrado en {PROMPTS_PATH}")
        sys.exit(1)

    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        prompts = json.load(f)
        
    semaforo = asyncio.Semaphore(MAX_CONCURRENCY)
    tareas = [procesar_chunk(semaforo, p) for p in prompts]
    
    print(f"Ejecutando extracción asíncrona ({len(prompts)} bloques) con {MODEL}...")
    resultados = await asyncio.gather(*tareas)
    
    exitos = sum(1 for _, estado in resultados if estado == "OK")
    omitidos = sum(1 for _, estado in resultados if estado == "Omitido")
    errores_sintaxis = sum(1 for _, estado in resultados if "Sintaxis TTL inválida" in estado)
    errores_red = sum(1 for _, estado in resultados if estado.startswith("Error") and "Sintaxis" not in estado)
    
    print("-" * 40)
    print("RESUMEN DE EXTRACCIÓN T-BOX")
    print("-" * 40)
    print(f"Generados válidos  : {exitos}")
    print(f"Omitidos           : {omitidos}")
    print(f"Errores Sintaxis   : {errores_sintaxis}")
    print(f"Errores API/Red    : {errores_red}")

if __name__ == "__main__":
    asyncio.run(orquestar_extraccion())