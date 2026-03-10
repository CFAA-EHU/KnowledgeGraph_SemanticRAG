# Knowledge Graph Pipeline — Semantic RAG

Pipeline completo de extracción, construcción y consulta de grafos de conocimiento a partir de manuales técnicos, con bucle de refinamiento iterativo.

## Arquitectura del Pipeline

```
Manual Técnico (PDF/TXT)
        │
        ▼
┌─────────────────────┐
│  Tarea 1: Ingesta   │  → Chunking dinámico con análisis de densidad
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Tarea 2: Extracción│  → CoT → Entidades + Relaciones → TTL
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Tarea 3: Merging   │  → Fusión en Triple Store (GraphDB)
└─────────┬───────────┘
          │
        ┌─┴──────────────────────┐
        ▼                        ▼
┌──────────────┐       ┌─────────────────────┐
│  Tarea 4:    │       │  Tarea 5: SPARQL     │
│  Golden Set  │       │  Generación + Val.   │
└──────┬───────┘       └──────────┬──────────┘
       │                          │
       └──────────┬───────────────┘
                  ▼
        ┌─────────────────────┐
        │  Tarea 6: Ejecución │  → Métricas vs Golden Set
        └─────────┬───────────┘
                  │
                  ▼
        ┌─────────────────────┐
        │  Tarea 7: Diagnóst. │  → Clasificación de errores
        └─────────┬───────────┘
                  │
                  ▼
        ┌─────────────────────┐
        │  Tarea 8: Refinem.  │  → Inyección + Re-loop ↺
        └─────────────────────┘
```
