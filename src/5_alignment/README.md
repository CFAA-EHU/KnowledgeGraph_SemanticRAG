# src/5_alignment — Alineamiento experimental de A-Box

Este directorio contiene utilidades experimentales de alineamiento semántico de instancias A-Box.

## Objetivo
Reducir duplicación de entidades en `abox_merged.ttl` mediante clustering semántico sobre etiquetas o literales descriptivos.

## Script principal

### `semantic_reduction.py`
Lee:
- `data/processed/abox_merged.ttl`

Genera:
- `data/processed/abox_aligned.ttl`

## Estado actual
El alineamiento de A-Box **no forma parte del carril operativo por defecto**.

Se conserva como paso experimental para:
- análisis de duplicidad
- reducción semántica
- pruebas de consolidación posterior

## Nota importante
El runtime operativo actual consume:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_merged.ttl`

No consume `abox_aligned.ttl` como artefacto oficial de producción.

## Cuándo usarlo
Usa este módulo solo si quieres evaluar:
- deduplicación de entidades
- impacto del clustering semántico sobre consultas
- posibles futuras mejoras del carril operativo