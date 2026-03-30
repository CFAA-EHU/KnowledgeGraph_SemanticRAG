# src/2_extraction - Carril experimental T-Box

Este directorio se conserva como tooling experimental para generar prompts T-Box y extraer TTLs conceptuales con LLM.

## Estado actual

No forma parte del runtime operativo actual.

El runtime vigente se construye con:
- `run_operational_pipeline.py`
- `src/6_extraction/`
- `src/8_retrieval/`
- `src/7_database/`

Este modulo sigue siendo util para:
- regenerar prompts T-Box con vocabulario controlado
- comparar salidas TTL exploratorias antes de integrarlas en el carril operativo
- hacer pruebas aisladas sobre modelado conceptual

## Scripts

### `prompt_assembler.py`
- lee `density_report.json` y `cache/terms_cache.json`
- monta prompts T-Box con vocabulario controlado
- genera `data/processed/tbox_prompts.json`

### `llm_extractor.py`
- consume `data/processed/tbox_prompts.json`
- llama al modelo configurado
- valida sintaxis Turtle con `rdflib`
- guarda TTLs en `data/processed/graphs/`

## Artefactos

- `data/processed/tbox_prompts.json`
- `data/processed/graphs/*.ttl`

## Importante

- Este carril es experimental y no define el runtime por defecto.
- Los TTLs generados aqui no se publican automaticamente en GraphDB ni se usan en el evaluador formal.
- Si se usa este modulo, debe tratarse como una exploracion separada del carril operativo A-Box.
