# Módulo 2: Ensamblaje de Prompts y Extracción Semántica (LLM)

Este módulo representa el motor de transformación del Gemelo Digital Cognitivo. Su responsabilidad es tomar los fragmentos de texto (chunks) previamente filtrados y aprobados por el Módulo de Ingesta, y utilizar Modelos Fundacionales (Mistral) para extraer entidades, propiedades y relaciones, transformando texto no estructurado en conocimiento computable (RDF/Turtle).

A diferencia de llamadas directas a APIs de LLMs, este módulo implementa inyección de contexto dinámico (Dynamic RAG) en la fase de generación del prompt y un bucle de validación sintáctica estricta (Auto-Healing) en la fase de extracción.

---

## Orden de Ejecución y Arquitectura del Flujo

1. **`prompt_assembler.py` (Ensamblaje y Contextualización):** Prepara las instrucciones exactas para el LLM.
2. **`llm_extractor.py` (Extracción Asíncrona y Validación):** Ejecuta las llamadas a la API, compila el resultado y lo guarda de forma segura.

---

## Descripción Detallada de los Códigos

### 1. `prompt_assembler.py` (Ensamblador de Prompts Dinámicos)
Este script actúa como el puente entre el análisis de densidad (Módulo 1) y el LLM. Su objetivo es restringir la libertad del modelo para evitar alucinaciones.

* **Inyección de Vocabulario Dinámico:** Lee el `terms_cache.json` y el reporte de densidad. Para cada fragmento de texto, identifica qué términos técnicos están presentes y genera un mapeo estricto de Término -> URI.
* **Ingeniería de Prompt Estricta:** Ensambla una instrucción compleja que obliga al LLM a:
  * Actuar como un Ingeniero de Conocimiento en Web Semántica.
  * Utilizar razonamiento interno paso a paso (Chain of Thought).
  * Limitarse a usar **únicamente** las URIs proporcionadas en el vocabulario dinámico para asegurar la coherencia del grafo (Entity Resolution en tiempo de extracción).
* **Salida:** Genera un archivo JSON consolidado con todos los prompts listos para ser consumidos de manera eficiente.

### 2. `llm_extractor.py` (Motor de Extracción y Validación Sintáctica)
Es el cliente asíncrono que interactúa con la API de Mistral. Está diseñado para ser tolerante a fallos, respetuoso con los límites de cuota (Rate Limits) y estrictamente riguroso con la sintaxis del código generado.

* **Concurrencia Controlada:** Utiliza `asyncio.Semaphore` para limitar el número de llamadas simultáneas a la API, evitando errores `HTTP 429 Too Many Requests`.
* **Aislamiento de Código:** Extrae exclusivamente los bloques de código (mediante expresiones regulares) de la respuesta conversacional del LLM.
* **Compilación y Auto-Corrección (Self-Healing Loop):** * Este es el núcleo crítico del script. Cada respuesta generada en formato Turtle (`.ttl`) es interceptada e intentada compilar en memoria utilizando la librería `rdflib`.
  * Si el LLM comete un error de sintaxis (ej. falta de puntos finales, prefijos no declarados), el script atrapa la excepción del compilador, la anexa como retroalimentación al prompt original y lanza un **reintento automático**.
  * El LLM dispone de hasta 3 intentos para corregir su propio código.
* **Manejo de Estados:** Registra minuciosamente qué fragmentos tuvieron éxito, cuáles fueron omitidos y cuáles fallaron definitivamente por red o sintaxis intratable.

---

## Uso y Ejecución

Para ejecutar la extracción de forma aislada (asumiendo que los reportes del Módulo 1 ya existen en `data/raw/` o la ruta configurada):

**Paso 1: Generar los Prompts**
```bash
python src/2_extraction/prompt_assembler.py
