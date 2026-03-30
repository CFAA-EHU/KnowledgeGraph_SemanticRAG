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

## Runtime Operativo

El planificador semántico, la recuperación (*retrieval*), la evaluación y la orquestación consumen los siguientes artefactos consolidados:
* `ontology_aligned.ttl`: La T-Box formal.
* `abox_linked.ttl`: La A-Box operativa final.
* `multilingual_lexicon.json`: El diccionario de superficies.

### Capas del A-Box
El flujo de extracción genera cuatro capas incrementales separadas para garantizar la trazabilidad:
1.  **`abox_merged.ttl`:** Snapshot bruto post-merge para diagnóstico.
2.  **`abox_canonical.ttl`:** Snapshot canónico intermedio para consolidación estructural.
3.  **`abox_enriched.ttl`:** Snapshot enriquecido intermedio para *linking* y *value surfaces* genéricos.
4.  **`abox_linked.ttl`:** Snapshot operativo final con *link completion* residual de alta confianza.

### Backends de Consulta (Post-T23)
El runtime mantiene dos backends de consulta para ejecutar las sentencias SPARQL generadas por el planificador:
* **`rdflib` (En memoria):** Actúa como backend de referencia y por defecto.
* **`GraphDB` (Remoto/Local):** Actúa como backend espejo opcional del mismo grafo operativo para publicación, verificación y smoke tests.

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
## Entrypoints Oficiales (Ejecución)

1.  **Pipeline Operativo:** Ejecuta la secuencia completa de construcción del grafo: abox_input_builder, abox_extractor, abox_merger, abox_canonicalizer, abox_graph_enricher, abox_link_completer y multilingual_lexicon_builder.

- Recuperación/Ejecución del pipeline sobre el estado actual:
```python run_operational_pipeline.py --mode resume-compatible```

- Onboarding piloto de un manual nuevo:
```python run_operational_pipeline.py --source-chunks data/raw/chunks_8070_quick_ref.txt --manual-id 8070_quick_ref --mode resume-compatible```

2.  **Workbench de Consultas:** El script query_workbench.py permite probar preguntas nuevas interactivamente. Muestra la traza completa de ejecución: intención detectada, ancla, idioma normalizado, familia de plan, profundidad prevista (boundedness), evidencia recuperada, evidencia seleccionada y respuesta sintetizada.

- Consulta usando el backend en memoria (por defecto):
```python query_workbench.py "¿Qué directiva cumple la máquina?"``` 

3.  **Benchmarks Formales (Evaluador QA):** Verifica que las implementaciones de enrutamiento no rompan los baselines establecidos.

- Validaciones de regresión:
```python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_canonical.json```
```python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json```

4.  **Integración con GraphDB:** Scripts para publicar la A-Box final en Ontotext GraphDB y monitorizar su estado de salud.

- Comandos de publicación y revisión:
```python src/7_database/graphdb_healthcheck.py```
```python src/7_database/publish_to_graphdb.py```

5. **Sandbox Diagnóstico:** Entorno para validación de resolución de entidades, promoción estructural y convergencia ES/EN. Utiliza QA_sandbox.json (diagnóstico estructural) y QA_bilingual.json (validación de que diferentes idiomas convergen en la misma intención, familia, ancla y SPARQL).

- Ejecución:
```python src/8_retrieval/qa_sandbox_diagnostic.py```


## Carriles del Repositorio
La arquitectura define la separación estricta entre experimentación y el entorno productivo. La fuente única de verdad para rutas y contratos de lectura/escritura reside en artifact_contracts.py.

- Carril Experimental: Se conserva para exploración y pruebas aisladas, pero no define el runtime por defecto.
- Carril Operativo: Es el camino oficial de build, consulta y evaluación.

Utilidades experimentales todavía conservadas:
- `src/2_extraction/` para prompts T-Box y extracción TTL exploratoria.
- `src/3_merging/graph_merger.py` para fusionar TTLs del carril T-Box experimental.
- `src/5_alignment/semantic_reduction.py` para pruebas de alineamiento semántico fuera del runtime.

Ninguna de esas piezas participa en el build, la consulta ni la evaluación del runtime operativo actual.

Tooling histórico de campaña en la raíz:
- `run_t25_sequential_integration.py`
- `run_t25_2_installation_recovery.py`
- `run_t26_error_manual_onboarding.py`

Se conservan por trazabilidad de onboarding y recuperación, pero no son entrypoints del runtime diario.

## Artefactos Clave del Carril Operativo
El pipeline productivo genera y consume los siguientes artefactos en el directorio data/processed/:

## Grafos y Ontología:
- ontology_aligned.ttl
- abox_input.json
- abox_merged.ttl
- abox_canonical.ttl
- abox_enriched.ttl
- abox_linked.ttl
- schema_condensed.txt

## Lexicón y Normalización:
- multilingual_lexicon.json
- language_detection_report.json
- canonical_entity_map.json

## Reportes de Construcción (A-Box):
- canonicalization_report.json
- enrichment_report.json
- enrichment_link_map.json / enrichment_surface_map.json
- link_completion_report.json / link_completion_map.json / link_completion_candidates.json
- link_completion_eval_report.json / link_completion_decision_report.json

## Reportes de Base de Datos (GraphDB):
- graphdb_publication_report.json
- graphdb_equivalence_report.json
- t23_graphdb_decision_report.json

## Evaluaciones de Enrutamiento (Planner):
- quick_ref_density_report.json / quick_ref_abox_input.json / quick_ref_onboarding_report.json
- quick_ref_bilingual_eval_report.json / quick_ref_bilingual_debug_report.json
- quick_ref_integration_decision_report.json
- quick_ref_v2_eval_report.json / quick_ref_v2_debug_report.json / quick_ref_v2_planner_alignment_report.json
- cross_eval_report.json / cross_debug_report.json / cross_planner_alignment_report.json
- t21_readiness_decision_report.json
- t22_planner_eval_report.json / t22_planner_decision_report.json

## Catálogos de Planes:
- planner_generalization_catalog_v2.json
- cross_plan_catalog.json


## Licencia
Este proyecto se distribuye bajo la Licencia MIT. Para más detalles, consulte el archivo LICENSE incluido en el repositorio. Configuración del Entorno
