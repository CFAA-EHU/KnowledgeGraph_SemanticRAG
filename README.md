# SemanticRAG: Gemelo Digital Cognitivo (Fagor 8070)

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)
![GraphDB](https://img.shields.io/badge/GraphDB-Semantic_Graph-orange?logo=databricks&logoColor=white)
![Mistral AI](https://img.shields.io/badge/Mistral_AI-LLM_Engine-black?logo=mistral&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)

SemanticRAG es un sistema avanzado de Retrieval-Augmented Generation (RAG) basado en semántica, diseñado específicamente para ingerir, estructurar e interrogar la documentación técnica de los controladores CNC Fagor 8070. El sistema procesa manuales de instalación, operación y resolución de errores, transformando texto no estructurado en conocimiento computable.

A diferencia de las arquitecturas RAG vectoriales estándar, este proyecto implementa un Grafo de Conocimiento (Knowledge Graph) respaldado por una ontología formal (T-Box) y aserciones de datos extraídas (A-Box). Este enfoque semántico mitiga el riesgo de alucinaciones al forzar al modelo fundacional (Mistral) a traducir el lenguaje natural del usuario en consultas SPARQL deterministas, garantizando respuestas precisas y referenciadas.

---

## Arquitectura del Sistema

La arquitectura se divide en cuatro subsistemas principales:

1.  **Ingesta y Extracción de Conocimiento (A-Box):** El pipeline fragmenta los manuales técnicos (ej. `chunks_man_8070_err.txt`) en micro-lotes. Utilizando LLMs configurados con perfiles de recuperación conservadores (para respetar límites de tasa de API), extrae entidades (componentes, parámetros, alarmas) y las relaciones estructurales definidas en la ontología.
2.  **Almacenamiento Semántico:** Los triplos RDF resultantes se consolidan en un repositorio local y se sincronizan con **Ontotext GraphDB**, que actúa como el motor de base de datos de grafos principal.
3.  **Enrutamiento Cognitivo (Planner):** Un planificador semántico interpreta la intención de la consulta del usuario, la clasifica en familias predefinidas de resolución y genera la consulta SPARQL correspondiente para recuperar la evidencia exacta del grafo.
4.  **Síntesis y Evaluación:** La evidencia recuperada se sintetiza en lenguaje natural. El sistema incluye un motor de evaluación riguroso que valida el rendimiento contra conjuntos de pruebas (*Golden Sets*) para detectar regresiones operativas.

---

## Requisitos Previos

La ejecución de este proyecto requiere la configuración de dependencias externas críticas:

* **Ontotext GraphDB:** Instancia activa (local o remota) para el alojamiento del repositorio semántico.
* **Mistral AI:** Clave de API válida con acceso a los modelos `mistral-small-latest` y `mistral-medium-latest`.
* **Python:** Versión 3.10 o superior.

---

## Instalación

1.  Clonar el repositorio en el entorno local:
    ```bash
    git clone
    cd KnowledgeGraph_SemanticRAG
    ```

2.  Crear y activar un entorno virtual para aislar las dependencias:
    ```bash
    python -m venv venv
    ```
    *En sistemas Windows:*
    ```bash
    venv\Scripts\activate
    ```
    
3.  Instalar las dependencias requeridas:
    ```bash
    pip install -r requirements.txt
    ```

---

## Configuración del Entorno

El sistema utiliza variables de entorno para gestionar credenciales y configuración de infraestructura. Cree un archivo `.env` en el directorio raíz del proyecto con el siguiente formato:

```env
# Clave de API de Mistral AI
MISTRAL_API_KEY=su_clave_api_aqui

# Modelo LLM predeterminado para operaciones estándar
MISTRAL_MODEL=mistral-small-latest

# Configuración de conexión a Ontotext GraphDB
GRAPHDB_URL=http://localhost:7200
GRAPHDB_REPO= semanticrag_operational_mirror