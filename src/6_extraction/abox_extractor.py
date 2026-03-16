import asyncio
import json
import re
import os
import sys
from pathlib import Path

from mistralai.client import Mistral
from rdflib import Graph

PROMPTS_PATH = Path("data/processed/tbox_prompts.json")
TBOX_PATH = Path("data/processed/ontology_aligned.ttl")
OUTPUT_DIR = Path("data/processed/abox_graphs/")
MAX_CONCURRENCY = 1
MODEL = "mistral-small-latest"
BASE_URI = "https://vocab.cfaa.eus/broaching/"

api_key = api_key = "HMXKoCPyStwJ9DjLnGQbKYMg2KqCiEUs" #os.environ.get("MISTRAL_API_KEY")
if not api_key:
    print("Error: Define la variable de entorno MISTRAL_API_KEY antes de ejecutar.")
    sys.exit(1)

client = Mistral(api_key=api_key)

def compilar_vocabulario_tbox() -> str:
    if not TBOX_PATH.exists():
        print(f"Error: No se encuentra el T-Box en {TBOX_PATH}")
        sys.exit(1)

    g = Graph()
    g.parse(TBOX_PATH, format="turtle")
    
    clases = set()
    obj_props = set()
    data_props = set()
    
    for s, p, o in g:
        tipo = str(o)
        nombre = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
        if "Class" in tipo:
            clases.add(nombre)
        elif "ObjectProperty" in tipo:
            obj_props.add(nombre)
        elif "DatatypeProperty" in tipo:
            data_props.add(nombre)
            
    return f"""
    VOCABULARIO ESTRICTO PERMITIDO:
    - Clases: {', '.join(clases)}
    - Propiedades de Objeto: {', '.join(obj_props)}
    - Propiedades de Datos: {', '.join(data_props)}
    """

def aislar_sintaxis_ttl(respuesta_llm: str) -> str:
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

async def procesar_chunk_abox(semaforo: asyncio.Semaphore, chunk_data: dict, vocabulario: str):
    chunk_id = chunk_data["chunk_id"]
    texto_original = chunk_data["prompt"]
    archivo_salida = OUTPUT_DIR / f"chunk_{chunk_id:03d}_abox.ttl"
    
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
                            "content": f"Eres un extractor de grafos de conocimiento RDF (A-Box). Extrae individuos e instancias del texto proporcionado. Usa el prefijo ex: <{BASE_URI}>. ESTÁ ESTRICTAMENTE PROHIBIDO inventar nuevas clases o propiedades que no estén en la siguiente lista. Si un concepto no encaja, omítelo.\n\n{vocabulario}"
                        },
                        {
                            "role": "user", 
                            "content": f"Extrae los individuos de este texto en formato Turtle (TTL) válido. No incluyas explicaciones:\n\n{texto_original}"
                        }
                    ]
                )
                
                ttl_puro = aislar_sintaxis_ttl(respuesta.choices[0].message.content)
                
                if not validar_sintaxis_rdf(ttl_puro):
                    if intento == 2:
                        return chunk_id, "Error: Sintaxis TTL inválida persistente"
                    await asyncio.sleep(2)
                    continue
                
                with open(archivo_salida, "w", encoding="utf-8") as f:
                    f.write(ttl_puro)
                    
                return chunk_id, "OK"
                
            except Exception as e:
                if intento == 2:
                    return chunk_id, f"Error de red/API: {str(e)}"
                await asyncio.sleep(5)

async def orquestar_extraccion_abox():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    if not PROMPTS_PATH.exists():
        print(f"Error: Archivo de datos no encontrado en {PROMPTS_PATH}")
        sys.exit(1)

    print("Compilando vocabulario del T-Box...")
    vocabulario = compilar_vocabulario_tbox()

    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        prompts = json.load(f)
        
    semaforo = asyncio.Semaphore(MAX_CONCURRENCY)
    tareas = [procesar_chunk_abox(semaforo, p, vocabulario) for p in prompts]
    
    print(f"Ejecutando extracción A-Box ({len(prompts)} bloques) con {MODEL}...")
    resultados = await asyncio.gather(*tareas)
    
    exitos = sum(1 for _, estado in resultados if estado == "OK")
    omitidos = sum(1 for _, estado in resultados if estado == "Omitido")
    errores = sum(1 for _, estado in resultados if estado.startswith("Error"))
    
    print("-" * 40)
    print("RESUMEN DE EXTRACCIÓN A-BOX")
    print("-" * 40)
    print(f"Generados válidos  : {exitos}")
    print(f"Omitidos (caché)   : {omitidos}")
    print(f"Errores totales    : {errores}")

if __name__ == "__main__":
    asyncio.run(orquestar_extraccion_abox())