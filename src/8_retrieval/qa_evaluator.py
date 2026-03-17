import json
import os
import sys
import re
import time
from pathlib import Path
from mistralai.client import Mistral
from rdflib import Graph
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import logging

logger = logging.getLogger(__name__)

QA_FILE = Path("data/golden_set/QA2.txt")
TBOX_PATH = Path("data/processed/ontology_aligned.ttl")
ABOX_PATH = Path("data/processed/abox_merged.ttl")
MODEL = "mistral-small-latest"
BASE_URI = "https://vocab.cfaa.eus/broaching/"

def cargar_grafo_memoria() -> Graph:
    if not TBOX_PATH.exists():
        logger.error(f"Error: No se encuentra T-Box en {TBOX_PATH}")
        sys.exit(1)
    if not ABOX_PATH.exists():
        logger.error(f"Error: No se encuentra A-Box en {ABOX_PATH}")
        sys.exit(1)
        sys.exit(1)
    g = Graph()
    g.parse(TBOX_PATH, format="turtle")
    g.parse(ABOX_PATH, format="turtle")
    return g

def aislar_sparql(respuesta_llm: str) -> str:
    patron = r"`{3}(?:sparql)?\n(.*?)`{3}"
    match = re.search(patron, respuesta_llm, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else respuesta_llm.strip()

class EvaluadorRAG:
    def __init__(self):
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            print("Error: Variable MISTRAL_API_KEY no definida.")
            sys.exit(1)
            
        self.client = Mistral(api_key=api_key)
        logger.info("Cargando Grafo de Conocimiento...")
        self.grafo = cargar_grafo_memoria()
        self.esquema = self._cargar_esquema_condensado()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda retry_state: print(f"Rate Limit detectado. Reintentando (Intento {retry_state.attempt_number})...")
    )

    def _cargar_esquema_condensado(self) -> str:
        ruta_esquema = Path("data/processed/schema_condensed.txt")
        if not ruta_esquema.exists():
            print("ADVERTENCIA: No se encontró el esquema condensado. El LLM operará a ciegas.")
            return "No disponible."
        with open(ruta_esquema, "r", encoding="utf-8") as f:
            return f.read()
        
    def _llamada_llm_segura(self, mensajes: list) -> str:
        respuesta = self.client.chat.complete(
            model=MODEL,
            temperature=0.0,
            messages=mensajes
        )
        return respuesta.choices[0].message.content

    def generar_consulta_sparql(self, pregunta: str) -> str:
        prompt = f"""
        Eres un experto en SPARQL para Grafos de Conocimiento de extracción abierta.
        Prefijo: PREFIX ex: <{BASE_URI}>
        
        ESQUEMA DE REFERENCIA (Úsalo para identificar Clases, no asumas que las Propiedades existen):
        {self.esquema}

        ESTRATEGIA DE RECUPERACIÓN ROBUSTA:
        1. Identifica los 2 conceptos clave.
        2. Para cada concepto, usa un bloque de búsqueda que ignore el nombre exacto de la propiedad (usa una variable ?p).
        3. Une los conceptos mediante una variable común para permitir el razonamiento multisalto.
        4. Usa FILTER(REGEX(...)) para capturar variaciones léxicas en los literales.

        PATRÓN OBLIGATORIO:
        SELECT DISTINCT ?s ?p ?o WHERE {{
          ?s ?p ?o .
          # Bloque Concepto 1
          {{
            ?s ?p1 ?o1 .
            FILTER(regex(str(?s), "concepto1|sinonimo", "i") || regex(str(?o1), "concepto1|sinonimo", "i"))
          }}
          # Bloque Concepto 2 (unido al primero para asegurar relevancia)
          {{
            ?s ?p2 ?o2 .
            FILTER(regex(str(?s), "concepto2|sinonimo", "i") || regex(str(?o2), "concepto2|sinonimo", "i"))
          }}
        }} LIMIT 100
        
        Responde EXCLUSIVAMENTE con el código SPARQL.
        """
        
        mensajes = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Pregunta: {pregunta}"}
        ]
        return aislar_sparql(self._llamada_llm_segura(mensajes))
    

    def sintetizar_respuesta(self, pregunta: str, tripletas_crudas: list) -> str:
        if not tripletas_crudas:
            return "[VACÍO] No se encontraron relaciones en el grafo para esta pregunta."
            
        contexto_str = "\n".join([f"- {s} | {p} | {o}" for s, p, o in tripletas_crudas])
        
        prompt = """
        Eres el asistente de un sistema RAG Semántico.
        Responde a la pregunta basándote ÚNICAMENTE en el Contexto Extraído.
        Redacta una respuesta directa y concisa. Cero explicaciones sobre cómo encontraste la información.
        """
        
        mensajes = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Pregunta: {pregunta}\n\nContexto Extraído:\n{contexto_str}"}
        ]
        return self._llamada_llm_segura(mensajes)

    def _normalizar_uri(self, uri: str) -> str:
        if not uri:
            return ""
        return str(uri).split("/")[-1].split("#")[-1]

    def ejecutar_evaluacion(self):
        with open(QA_FILE, "r", encoding="utf-8") as f:
            datos_qa = json.load(f)

        banco_preguntas = []
        for bloque in datos_qa:
            for item in bloque.get("questions", []):
                # Se extrae expected_uris, si no existe devuelve una lista vacía
                banco_preguntas.append((
                    item["question"], 
                    item["answer"], 
                    item.get("expected_uris", [])
                ))

        print(f"Iniciando evaluación de {len(banco_preguntas)} preguntas con pipeline completo...\n")

        # Se desempaqueta uris_esperadas en el iterador
        for i, (pregunta, respuesta_esperada, uris_esperadas) in enumerate(banco_preguntas, 1):
            print("=" * 70)
            print(f"PREGUNTA {i}/{len(banco_preguntas)}: {pregunta}")
            print(f"ESPERADA: {respuesta_esperada}")
            print("-" * 70)
            
            try:
                sparql_query = self.generar_consulta_sparql(pregunta)
                print("SPARQL GENERADA:\n" + sparql_query)
                print("-" * 70)
                
                resultados = self.grafo.query(sparql_query)
                
                tripletas_limpias = []
                uris_recuperadas = set() # Set para almacenar las URIs completas recuperadas
                
                for fila in resultados:
                    # Limpieza para inyectar en el LLM de síntesis
                    s = str(fila[0]).split("/")[-1].split("#")[-1]
                    p = str(fila[1]).split("/")[-1].split("#")[-1]
                    o = str(fila[2]).split("/")[-1].split("#")[-1]
                    tripletas_limpias.append((s, p, o))
                    
                    # Almacenamiento de URIs completas para la evaluación matemática
                    uris_recuperadas.update([str(fila[0]), str(fila[1]), str(fila[2])])
                    
                print(f"Nodos recuperados totales: {len(tripletas_limpias)}")
                
                # --- INICIO LÓGICA MATEMÁTICA ---
                conjunto_esperado = {self._normalizar_uri(uri) for uri in uris_esperadas}
                uris_recuperadas_norm = {self._normalizar_uri(uri) for uri in uris_recuperadas}
                conjunto_esperado.discard("")
                uris_recuperadas_norm.discard("")
                nodos_correctos = uris_recuperadas_norm.intersection(conjunto_esperado)
                
                precision = len(nodos_correctos) / len(uris_recuperadas_norm) if uris_recuperadas_norm else 0.0
                recall = len(nodos_correctos) / len(conjunto_esperado) if conjunto_esperado else 0.0
                
                print(f"MÉTRICAS -> Precisión: {precision:.2f} | Recall: {recall:.2f}")
                # --- FIN LÓGICA MATEMÁTICA ---

                respuesta_final = self.sintetizar_respuesta(pregunta, tripletas_limpias)
                print(f"SINTETIZADA: {respuesta_final}")

            except Exception as e:
                print(f"Fallo crítico en la pregunta {i}: {e}")
            
            print("=" * 70 + "\n")
            time.sleep(3)

if __name__ == "__main__":
    evaluador = EvaluadorRAG()
    evaluador.ejecutar_evaluacion()