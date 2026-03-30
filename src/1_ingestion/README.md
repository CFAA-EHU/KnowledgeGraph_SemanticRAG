# Módulo 1: Ingesta, Filtrado Cognitivo y Análisis de Densidad

Este directorio contiene el "Kilómetro Cero" del pipeline del Gemelo Digital Cognitivo. A diferencia de los parsers de texto tradicionales, este módulo no se limita a extraer texto de documentos; actúa como un **filtro semántico y económico** antes de que la información alcance la fase de extracción con Modelos Fundacionales (LLMs).

Su objetivo principal es dotar al sistema de vocabulario técnico de la Industria 4.0, normalizar el texto, detectar el idioma a nivel de fragmento (chunk) y descartar el "ruido" (índices, portadas, texto de marketing) para **minimizar el consumo innecesario de tokens en la API de Mistral**.

---

## Orden de Ejecución y Arquitectura del Flujo

Aunque el punto de entrada principal para el usuario es el `density_analyzer.py`, la arquitectura subyacente sigue este orden lógico de dependencias:

1. **`termLoader.py` (Fase de Aprendizaje y Caché):** Se ejecuta para construir el diccionario de jerga técnica.
2. **`language_utils.py` (Fase de Normalización):** Actúa como librería de soporte en memoria para limpiar y clasificar el texto.
3. **`density_analyzer.py` (Fase de Análisis y Orquestación):** Orquesta a los dos anteriores, lee los archivos en bruto, cruza los datos y genera los fragmentos óptimos y reportes.

---

## Descripción Detallada de los Códigos

### 1. `termLoader.py`
Este script es responsable de construir la base de conocimiento léxico del sistema conectándose a fuentes de la Web Semántica y estándares industriales.

* **Función Principal:** Descarga conceptos técnicos de DBpedia (vía consultas SPARQL) y carga vocabularios estándar de *Asset Administration Shell* (AAS) como *Sensor*, *Actuator*, *NominalTorque*, etc.
* **Procesamiento Bilingüe:** Utiliza modelos de traducción local (`Helsinki-NLP/opus-mt-en-es` de HuggingFace) para garantizar que cada término industrial tenga su equivalente en inglés y español.
* **Gestión de Caché:** Para evitar latencias de red y bloqueos por límite de peticiones (Rate Limits) en APIs públicas, serializa todos los términos traducidos y enriquecidos en un archivo local: `cache/terms_cache.json`. Posee un *Time-to-Live* (TTL) configurable (por defecto, 30 días).

### 2. `language_utils.py`
Una librería de utilidades de alto rendimiento diseñada para procesar texto a nivel de caracteres y palabras.

* **Normalización (`normalize_text`):** Convierte caracteres Unicode (elimina tildes y marcas diacríticas), pasa el texto a minúsculas y elimina caracteres especiales no alfanuméricos mediante expresiones regulares. Esto garantiza que el analizador de densidad no falle por variaciones tipográficas.
* **Detección de Idioma Matemática (`detect_language`):** En lugar de usar modelos pesados para detectar el idioma, utiliza heurísticas de alta velocidad basadas en la intersección de *stopwords* industriales específicas (ej. "mantenimiento", "advertencia" vs. "maintenance", "safety"). Devuelve el idioma (`es` o `en`) junto con un coeficiente de confianza (confidence score).
* **Extracción de Superficies (`iter_term_surfaces`):** Expande cada entrada del diccionario en múltiples variaciones (aliases) para maximizar la tasa de acierto (Hit Rate) durante el análisis de texto.

### 3. `density_analyzer.py`
Es el script orquestador del módulo y el filtro principal de datos. Recibe un archivo de fragmentos (chunks) de texto y decide cuáles valen la pena enviar al LLM.

* **Motor NLP y Tokenización:** Instancia un pipeline ligero de `spacy` para la segmentación de oraciones (sentencizer) y utiliza `tiktoken` (cl100k_base) para medir exactamente cuántos tokens le costará cada bloque a la API.
* **Cálculo de Densidad (`HIGH_DENSITY_THRESHOLD`):** Compara el número de términos técnicos (importados por `termLoader`) que aparecen en un chunk contra su tamaño total en tokens. 
* **Clasificación y Poda:** * `HIGH_DENSITY`: Párrafos ricos en conocimiento técnico. Se aprueban para la fase de extracción (A-Box).
  * `LOW_DENSITY` / `NO_ENTITIES`: Índices, páginas en blanco o introducciones genéricas. Se etiquetan para ser ignorados o procesados con modelos más baratos.
* **Generación de Artefactos:** Escribe el reporte detallado de densidad y el mapa de detección de idiomas en el directorio `data/processed/`, garantizando la trazabilidad de qué se descartó y por qué.

---

## Uso y Ejecución

El pipeline de ingesta se puede ejecutar de forma independiente para auditar un manual antes de pasarlo a la fase de extracción semántica.

**Comando básico:**
Evalúa un archivo de texto fragmentado y genera los reportes de densidad.
```bash
python src/1_ingestion/density_analyzer.py --input data/raw/chunks_man_8070_err.txt
