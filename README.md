# KnowledgeGraph_SemanticRAG
Pipeline de Knowledge Graph con RAG semántico

/
├── .github/
│   ├── workflows/          # CI/CD (validación TTL, tests)
│   └── ISSUE_TEMPLATE/     # Plantillas para bugs, features
├── docs/                   # Documentación del pipeline
├── src/
│   ├── 1_ingestion/        # Tarea 1: Chunking dinámico
│   ├── 2_extraction/       # Tarea 2: Extracción CoT → TTL
│   ├── 3_merging/          # Tarea 3: Fusión del grafo
│   ├── 4_evaluation_set/   # Tarea 4: Dataset de preguntas
│   ├── 5_sparql/           # Tarea 5: Generación y validación SPARQL
│   ├── 6_execution/        # Tarea 6: Evaluación de respuestas
│   ├── 7_diagnostics/      # Tarea 7: Diagnóstico de fallos
│   └── 8_refinement/       # Tarea 8: Bucle iterativo
├── ontologies/             # Archivos .ttl generados
├── data/
│   ├── raw/                # Manuales originales
│   └── golden_set/         # Preguntas + respuestas esperadas
└── tests/
