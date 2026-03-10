# Documentación del Pipeline

## Índice
- [Tarea 1 — Ingesta y Segmentación](./task1_ingestion.md)
- [Tarea 2 — Extracción Atómica](./task2_extraction.md)
- [Tarea 3 — Merging del Grafo](./task3_merging.md)
- [Tarea 4 — Dataset de Evaluación](./task4_evaluation_set.md)
- [Tarea 5 — Interfaz SPARQL](./task5_sparql.md)
- [Tarea 6 — Ejecución y Métricas](./task6_execution.md)
- [Tarea 7 — Diagnóstico de Fallos](./task7_diagnostics.md)
- [Tarea 8 — Refinamiento Iterativo](./task8_refinement.md)

## Parámetros Globales

| Parámetro | Valor por defecto | Descripción |
|---|---|---|
| `CHUNK_OVERLAP` | 15–20% | Solapamiento entre bloques |
| `SBERT_THRESHOLD` | 0.85 | Umbral de similitud coseno |
| `SUCCESS_THRESHOLD` | 0.85 | Tasa de aciertos para terminar el loop |
| `MAX_ITERATIONS` | 5 | Iteraciones máximas del bucle |

## Variables de Entorno

Crear un archivo `.env` en la raíz del proyecto:

```env
LLM_API_KEY=sk-...
GRAPHDB_ENDPOINT=http://localhost:7200/repositories/kg-pipeline
GRAPHDB_USER=admin
GRAPHDB_PASSWORD=...
```
