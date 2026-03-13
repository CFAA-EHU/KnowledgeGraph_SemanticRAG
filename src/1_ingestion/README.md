# Tarea 1: Ingesta y Segmentación Dinámica

Módulo encargado de descubrir categorías ontológicas dinámicamente mediante procesamiento de lenguaje natural y segmentar físicamente el manual en bloques adaptativos respetando límites de tokens y semántica de oraciones.

## Archivos y Flujo de Datos

### termLoader.py
Descubre, carga y serializa los términos técnicos del dominio desde fuentes ontológicas externas mediante extracción Bottom-Up.

**Lógica de Extracción:**
- **Descubrimiento NLP:** Analiza el texto crudo del manual utilizando spaCy para aislar morfología nominal (sustantivos frecuentes).
- **ESDBpedia:** Cruza los sustantivos descubiertos mediante consultas SPARQL a es.dbpedia.org/sparql para identificar categorías enciclopédicas reales del equipo y extraer los términos técnicos asociados.
- **AAS / ECLASS:** Conceptos industriales paramétricos en inglés, traducidos al español con el modelo Helsinki-NLP (opus-mt-en-es).

**Caché:**
- La primera ejecución procesa el texto, consulta ontologías, traduce y guarda el resultado en cache/terms_cache.json.
- Estructura de salida: Lista de diccionarios conteniendo termino y uri. Expira a los 30 días.

---

### density_analyzer.py
Ejecuta el análisis de densidad técnica y la partición física del texto (chunking). Actúa como inyector de dependencias para termLoader.py.

**Entrada:** Archivo .txt con el manual pre-segmentado en cabeceras lógicas.

**Lógica de Densidad y Partición Física:**
1. **Medición de Densidad:** Calcula el ratio de términos técnicos (validados contra termLoader.py) sobre el total de palabras de una sección lógica.
2. **Parametrización:** - Densidad alta (≥ 5%): Límite de 256 tokens por bloque físico.
   - Densidad baja (< 5%): Límite de 512 tokens por bloque físico.
3. **Segmentación Segura (Sentence-safe):** Utiliza spaCy (sentencizer) para dividir el texto en oraciones lógicas. Nunca corta una frase a la mitad.
4. **Conteo de Tokens:** Emplea tiktoken (modelo cl100k_base) para medir la longitud estricta de las oraciones.
5. **Solapamiento Matemático (Overlap):** Retrocede dinámicamente en el array de oraciones previas hasta cubrir el 15% del límite de tokens del nuevo bloque. Esto preserva la trazabilidad de anáforas.

**Salida:** data/raw/density_report.json
El JSON resultante aplana la estructura, convirtiendo N secciones lógicas en M sub-bloques físicos (chunk_id), inyectando el texto cortado, la cuenta de tokens real y los metadatos de contexto (páginas, sección, título).

---

## Uso
Ejecutar análisis y partición física:
```
python src/1_ingestion/density_analyzer.py --input data/raw/chunks_manual_instrucciones_a218.txt
```

## Dependencias
Requiere instalación estricta de procesadores de lenguaje y clientes de red:
```
pip install SPARQLWrapper requests transformers sentencepiece spacy tiktoken
python -m spacy download es_core_news_sm
```
## **Integración con Tarea 2**

El archivo de salida density_report.json y el vocabulario en cache/terms_cache.json son consumidos directamente por src/2_extraction/prompt_assembler.py. Este script filtra bloques irrelevantes (< 50 caracteres) y ensambla las instrucciones dinámicas con Chain of Thought (CoT), inyectando metadatos para la resolución de anáforas y previniendo alucinaciones en la generación T-Box del LLM.
