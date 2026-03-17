import os
import sys
import re
from pathlib import Path
from mistralai.client import Mistral
from rdflib import Graph
import logging

logger = logging.getLogger(__name__)

TBOX_PATH = Path("data/processed/ontology_aligned.ttl")
ABOX_PATH = Path("data/processed/abox_merged.ttl")
MODEL = "mistral-small-latest"
BASE_URI = "https://vocab.cfaa.eus/broaching/"

def cargar_grafo_memoria() -> Graph:
    if not TBOX_PATH.exists() or not ABOX_PATH.exists():
        print("Error: Faltan archivos T-Box o A-Box.")
        sys.exit(1)
    g = Graph()
    g.parse(TBOX_PATH, format="turtle")
    g.parse(ABOX_PATH, format="turtle")
    return g

def aislar_sparql(respuesta_llm: str) -> str:
    patron = r"`{3}(?:sparql)?\n(.*?)`{3}"
    match = re.search(patron, respuesta_llm, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else respuesta_llm.strip()

def traducir_y_ejecutar(pregunta: str):
    api_key = os.environ.get("MISTRAL_API_KEY") #os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("Error: Variable MISTRAL_API_KEY no definida.")
        sys.exit(1)

    client = Mistral(api_key=api_key)
    grafo = cargar_grafo_memoria()

    prompt_sistema = f"""
    Eres un traductor de Lenguaje Natural a SPARQL exploratorio.
    Prefijo principal: PREFIX ex: <{BASE_URI}>
    
    REGLA ESTRICTA: NO inventes propiedades exactas (como ex:purpose o ex:model). No conoces el esquema de la base de datos.
    
    Para responder a la pregunta, debes generar una consulta que busque palabras clave de la pregunta dentro de las URIs o etiquetas del grafo y devuelva las relaciones adyacentes.
    
    Usa este patrón obligatorio:
    SELECT ?s ?p ?o WHERE {{
      ?s ?p ?o .
      FILTER(CONTAINS(LCASE(str(?s)), "palabra_clave_1") || CONTAINS(LCASE(str(?o)), "palabra_clave_1"))
    }} LIMIT 50
    
    Extrae 1 o 2 palabras clave fundamentales de la pregunta del usuario para el filtro.
    Responde EXCLUSIVAMENTE con el código SPARQL.
    """

    print(f"Procesando pregunta: {pregunta}")
    
    try:
        respuesta = client.chat.complete(
            model=MODEL,
            temperature=0.0,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": f"Genera la consulta SPARQL exploratoria para: {pregunta}"}
            ]
        )
        
        sparql_query = aislar_sparql(respuesta.choices[0].message.content)
        
        print("-" * 40)
        print("CONSULTA SPARQL GENERADA")
        print("-" * 40)
        print(sparql_query)
        print("-" * 40)

        resultados = grafo.query(sparql_query)
        
        print("RESULTADOS DE LA EXTRACCIÓN:")
        filas_obtenidas = list(resultados)
        
        if not filas_obtenidas:
            print("Vacío. La consulta no interceptó nodos en el grafo.")
        else:
            for fila in filas_obtenidas:
                # Formateo limpio para mostrar Sujeto | Predicado | Objeto
                print(" | ".join([str(val).split("/")[-1].split("#")[-1] for val in fila]))
                
    except Exception as e:
        print(f"Error en el proceso de recuperación: {e}")

if __name__ == "__main__":
    pregunta_prueba = "¿Para qué sirve el manual de la brochadora A218 / RASHEM - 7x3000x500?"
    traducir_y_ejecutar(pregunta_prueba)