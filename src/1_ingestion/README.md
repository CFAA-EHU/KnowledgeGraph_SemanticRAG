# src/1_ingestion

Ingestion, density analysis, and chunk filtering for the A-Box extraction pipeline.

## Execution order

1. `termLoader.py` — builds the technical terminology cache from ESDBpedia SPARQL, AAS/ECLASS standards, and local corpus frequency analysis. Result cached at `cache/terms_cache.json` (TTL: 30 days).
2. `language_utils.py` — in-memory library for text normalization, language detection, and token-level classification. Called by `density_analyzer.py`.
3. `density_analyzer.py` — main entrypoint. Orchestrates `termLoader.py` and `language_utils.py`, reads raw chunk files, assigns density scores, and produces `*_density_report.json` and `*_abox_input.json` per manual.

## termLoader.py

Builds the lexical knowledge base from three sources:

- ESDBpedia (dynamic category discovery via SPARQL against `https://es.dbpedia.org/sparql`)
- AAS/ECLASS concept descriptions (translated EN→ES using `Helsinki-NLP/opus-mt-en-es`)
- Local corpus frequency analysis (top-N nouns extracted via spaCy `es_core_news_sm`)

Cache path: `cache/terms_cache.json`. Force refresh: `python src/1_ingestion/termLoader.py --refresh --input <chunk_file>`.

## language_utils.py

Provides: language detection per chunk, bilingual surface normalization, and stop-word filtering. Consumed internally by `density_analyzer.py`.

## density_analyzer.py

Reads raw chunk files (structured text with page/section headers), cross-references against the terminology cache, scores each chunk by semantic density, and discards low-value fragments (covers, indices, blank pages, non-informative runs).

Output: `data/processed/<prefix>_density_report.json` and `data/processed/<prefix>_abox_input.json`.
