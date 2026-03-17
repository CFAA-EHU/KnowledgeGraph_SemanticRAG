import os
import sys
import re
from pathlib import Path
from mistralai.client import Mistral
from rdflib import Graph
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
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

class MotorRAGSemantico:
    def __init__(self):
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            print("Error: Variable MISTRAL_API_KEY no definida.")
            sys.exit(1)
            
        self.client = Mistral(api_key=api_key)
        logger.info("Cargando Grafo de Conocimiento (T-Box + A-Box)...")
        self.grafo = cargar_grafo_memoria()
        logger.info(f"Grafo inicializado con {len(self.grafo)} tripletas.")

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda retry_state: print(f"Rate Limit detectado. Reintentando llamada al LLM (Intento {retry_state.attempt_number})...")
    )
    def _llamada_llm_segura(self, mensajes: list) -> str:
        respuesta = self.client.chat.complete(
            model=MODEL,
            temperature=0.0,
            messages=mensajes
        )
        return respuesta.choices[0].message.content

    def generar_consulta_sparql(self, pregunta: str) -> str:
        prompt = f"""
        Eres un traductor experto de Lenguaje Natural a SPARQL exploratorio.
        Prefijo: PREFIX ex: <{BASE_URI}>
        
        REGLAS VITALES:
        1. NO asumas nombres de propiedades exactas. Usa búsqueda de texto flexible.
        2. EXTRAE 2 o 3 identificadores CLAVE de la pregunta (ej. códigos alfanuméricos como "A218", nombres propios, verbos principales). Ignora palabras genéricas si están solas.
        
        Usa este patrón:
        SELECT ?s ?p ?o WHERE {{
          ?s ?p ?o .
          FILTER(
            (CONTAINS(LCASE(str(?s)), "clave1") || CONTAINS(LCASE(str(?o)), "clave1")) &&
            (CONTAINS(LCASE(str(?s)), "clave2") || CONTAINS(LCASE(str(?o)), "clave2"))
          )
        }} LIMIT 30
        
        Responde EXCLUSIVAMENTE con el código SPARQL validado.
        """
        
        mensajes = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Genera la consulta SPARQL para: {pregunta}"}
        ]
        
        respuesta_cruda = self._llamada_llm_segura(mensajes)
        return aislar_sparql(respuesta_cruda)

    def sintetizar_respuesta(self, pregunta: str, tripletas_crudas: list) -> str:
        contexto_str = "\n".join([f"- {s} | {p} | {o}" for s, p, o in tripletas_crudas])
        
        prompt = """
        Eres el asistente final de un sistema RAG Semántico. 
        Tu tarea es responder a la pregunta del usuario utilizando ÚNICAMENTE la información proporcionada en el "Contexto Extraído del Grafo".
        - Si el contexto está vacío o no contiene la respuesta, di claramente "No dispongo de información en la base de datos para responder a esto."
        - No alucines información externa.
        - Redacta una respuesta natural, directa y concisa.
        """
        
        mensajes = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Pregunta: {pregunta}\n\nContexto Extraído del Grafo:\n{contexto_str}"}
        ]
        
        return self._llamada_llm_segura(mensajes)

    def consultar(self, pregunta: str):
        print("\n" + "="*50)
        print(f"USUARIO: {pregunta}")
        print("="*50)
        
        print("\n1. Agente Text-to-SPARQL trabajando...")
        sparql_query = self.generar_consulta_sparql(pregunta)
        # print("Query generada:\n", sparql_query) # Descomentar para debug
        
        print("2. Ejecutando búsqueda en el Grafo...")
        resultados = self.grafo.query(sparql_query)
        
        tripletas_limpias = []
        for fila in resultados:
            s = str(fila[0]).split("/")[-1].split("#")[-1]
            p = str(fila[1]).split("/")[-1].split("#")[-1]
            o = str(fila[2]).split("/")[-1].split("#")[-1]
            tripletas_limpias.append((s, p, o))
            
        print(f"   -> Se recuperaron {len(tripletas_limpias)} relaciones semánticas.")
        
        print("3. Agente de Síntesis redactando respuesta...")
        respuesta_final = self.sintetizar_respuesta(pregunta, tripletas_limpias)
        
        print("\n" + "-"*50)
        print("RESPUESTA RAG SEMÁNTICO:")
        print(respuesta_final)
        print("-"*50 + "\n")

if __name__ == "__main__":
    motor = MotorRAGSemantico()
    
    # Probando la pregunta que falló anteriormente
    motor.consultar("¿Para qué sirve el manual de la brochadora A218 / RASHEM - 7x3000x500?")