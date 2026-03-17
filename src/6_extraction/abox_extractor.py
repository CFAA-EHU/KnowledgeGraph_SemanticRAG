import asyncio
import json
import re
import os
import sys
from pathlib import Path
from mistralai.client import Mistral
from rdflib import Graph
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import logging
import tempfile

logger = logging.getLogger(__name__)

PROMPTS_PATH = Path("data/processed/tbox_prompts.json")
TBOX_PATH = Path("data/processed/ontology_aligned.ttl")
OUTPUT_DIR = Path("data/processed/abox_graphs/")
MAX_CONCURRENCY = 2
MODEL = "mistral-small-latest"
BASE_URI = "https://vocab.cfaa.eus/broaching/"

api_key = os.environ.get("MISTRAL_API_KEY")
if not api_key:
    print("Error: Define la variable de entorno MISTRAL_API_KEY antes de ejecutar.")
    sys.exit(1)

client = Mistral(api_key=api_key)

def compilar_vocabulario_tbox() -> str:
    if not TBOX_PATH.exists():
        logger.error(f"Error: No se encuentra T-Box en {TBOX_PATH}")
        sys.exit(1)
    g = Graph()
    g.parse(TBOX_PATH, format="turtle")
    clases, obj_props, data_props = set(), set(), set()
    for s, p, o in g:
        tipo = str(o)
        nombre = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
        if "Class" in tipo: clases.add(nombre)
        elif "ObjectProperty" in tipo: obj_props.add(nombre)
        elif "DatatypeProperty" in tipo: data_props.add(nombre)
    return f"- Clases: {', '.join(clases)}\n- ObjProps: {', '.join(obj_props)}\n- DataProps: {', '.join(data_props)}"

def aislar_sintaxis_ttl(respuesta_llm: str) -> str:
    patron = r"`{3}(?:turtle|ttl)?\n(.*?)`{3}"
    match = re.search(patron, respuesta_llm, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else respuesta_llm.strip()

def validar_sintaxis_rdf(ttl_data: str) -> bool:
    try:
        Graph().parse(data=ttl_data, format="turtle")
        return True
    except:
        return False

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    retry=retry_if_exception_type(Exception)
)
async def llamada_llm_con_reintento(mensajes: list) -> str:
    respuesta = await client.chat.complete_async(model=MODEL, temperature=0.0, messages=mensajes)
    return respuesta.choices[0].message.content

async def procesar_chunk_abox(semaforo: asyncio.Semaphore, chunk_data: dict, vocabulario: str):
    chunk_id = chunk_data["chunk_id"]
    texto_original = chunk_data["prompt"]
    archivo_salida = OUTPUT_DIR / f"chunk_{chunk_id:03d}_abox.ttl"
    
    if archivo_salida.exists():
        return chunk_id, "Omitido"

    prompt_sistema = f"""
    Eres un extractor de grafos de conocimiento RDF (A-Box). Usa el prefijo ex: <{BASE_URI}>.
    
    REGLAS CRÍTICAS DE EXTRACCIÓN:
    1. Usa estrictamente las Clases y Propiedades de este vocabulario:
    {vocabulario}
    
    2. ES OBLIGATORIO extraer valores literales específicos mencionados en el texto (correos electrónicos, códigos como 'A218', normativas como '2006/42/CE', nombres de empresas o advertencias).
    3. Si no existe una DatatypeProperty exacta en el vocabulario para guardar ese valor, DEBES asociar el valor literal a la instancia usando `rdfs:label` o `rdfs:comment`.
    Ejemplo: ex:InstanciaMaquina rdfs:comment "Modelo A218 / RASHEM - 7x3000x500" .
    """

    async with semaforo:
        try:
            contenido = await llamada_llm_con_reintento([
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": f"Extrae los individuos en formato Turtle (TTL):\n\n{texto_original}"}
            ])
            
            ttl_puro = aislar_sintaxis_ttl(contenido)
            if not validar_sintaxis_rdf(ttl_puro):
                return chunk_id, "Error: Sintaxis TTL inválida"
            
            with open(archivo_salida, "w", encoding="utf-8") as f:
                f.write(ttl_puro)
            return chunk_id, "OK"
            
        except Exception as e:
            return chunk_id, f"Error persistente: {str(e)}"

async def orquestar_extraccion_abox():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    vocabulario = compilar_vocabulario_tbox()

    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        prompts = json.load(f)
        
    semaforo = asyncio.Semaphore(MAX_CONCURRENCY)
    tareas = [procesar_chunk_abox(semaforo, p, vocabulario) for p in prompts]
    
    print(f"Ejecutando extracción A-Box ({len(prompts)} bloques) con {MODEL}...")
    resultados = await asyncio.gather(*tareas)
    
    exitos = sum(1 for _, estado in resultados if estado == "OK")
    omitidos = sum(1 for _, estado in resultados if estado == "Omitido")
    errores = sum(1 for _, estado in resultados if "Error" in estado)
    
    print(f"Generados válidos: {exitos} | Omitidos: {omitidos} | Errores: {errores}")

if __name__ == "__main__":
    asyncio.run(orquestar_extraccion_abox())