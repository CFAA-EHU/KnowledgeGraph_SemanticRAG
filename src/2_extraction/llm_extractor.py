import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import asyncio
import json
import os
import re
import sys

from mistralai.client import Mistral
from rdflib import Graph

from artifact_contracts import EXPERIMENTAL_TBOX_CHUNKS_DIR, EXPERIMENTAL_TBOX_PROMPTS_PATH

PROMPTS_PATH = EXPERIMENTAL_TBOX_PROMPTS_PATH
OUTPUT_DIR = EXPERIMENTAL_TBOX_CHUNKS_DIR
MAX_CONCURRENCY = 1
MODEL = "mistral-small-latest"

api_key = os.environ.get("MISTRAL_API_KEY")
if not api_key:
    print("Error: Define la variable de entorno MISTRAL_API_KEY antes de ejecutar.")
    sys.exit(1)

client = Mistral(api_key=api_key)

def extract_ttl_syntax(llm_response: str) -> str:
    pattern = r"`{3}(?:turtle|ttl)?\n(.*?)`{3}"
    match = re.search(pattern, llm_response, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return llm_response.strip()

def validar_sintaxis_rdf(ttl_data: str) -> bool:
    try:
        g = Graph()
        g.parse(data=ttl_data, format="turtle")
        return True
    except Exception:
        return False

async def procesar_chunk(semaforo: asyncio.Semaphore, chunk_data: dict):
    chunk_id = chunk_data["chunk_id"]
    prompt = chunk_data["prompt"]
    archivo_salida = OUTPUT_DIR / f"chunk_{chunk_id:03d}.ttl"

    # Transitional behavior: file-existence reuse remains here for now.
    if archivo_salida.exists():
        return chunk_id, "Omitido"

    async with semaforo:
        for intento in range(3):
            try:
                respuesta = await client.chat.complete_async(
                    model=MODEL,
                    temperature=0.0,
                    messages=[
                        {
                            "role": "system",
                            "content": "Eres un motor de serializacion RDF. Responde exclusivamente con sintaxis Turtle (TTL) valida. Omite explicaciones o texto conversacional. Genera modelo T-Box, prohibe individuos A-Box.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                )

                ttl_puro = extract_ttl_syntax(respuesta.choices[0].message.content)

                if not validar_sintaxis_rdf(ttl_puro):
                    if intento == 2:
                        return chunk_id, "Error: Sintaxis TTL invalida persistente"
                    await asyncio.sleep(2)
                    continue

                with open(archivo_salida, "w", encoding="utf-8") as f:
                    f.write(ttl_puro)

                return chunk_id, "OK"

            except Exception as e:
                if intento == 2:
                    return chunk_id, f"Error de red: {str(e)}"
                await asyncio.sleep(5)

async def orquestar_extraccion():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not PROMPTS_PATH.exists():
        print(f"Error: Archivo de prompts no encontrado en {PROMPTS_PATH}")
        sys.exit(1)

    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    semaforo = asyncio.Semaphore(MAX_CONCURRENCY)
    tareas = [procesar_chunk(semaforo, p) for p in prompts]

    print(f"Ejecutando extraccion asincrona ({len(prompts)} bloques) con {MODEL}...")
    resultados = await asyncio.gather(*tareas)

    exitos = sum(1 for _, estado in resultados if estado == "OK")
    omitidos = sum(1 for _, estado in resultados if estado == "Omitido")
    errores_sintaxis = sum(1 for _, estado in resultados if "Sintaxis TTL invalida" in estado)
    errores_red = sum(1 for _, estado in resultados if estado.startswith("Error") and "Sintaxis" not in estado)

    print("-" * 40)
    print("RESUMEN DE EXTRACCION T-BOX")
    print("-" * 40)
    print(f"Generados validos  : {exitos}")
    print(f"Omitidos           : {omitidos}")
    print(f"Errores Sintaxis   : {errores_sintaxis}")
    print(f"Errores API/Red    : {errores_red}")

if __name__ == "__main__":
    asyncio.run(orquestar_extraccion())
