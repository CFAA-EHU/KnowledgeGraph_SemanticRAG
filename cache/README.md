# cache

Terminology cache for `src/1_ingestion/termLoader.py`.

## terms_cache.json

Merged term list built from three sources:

- ESDBpedia: technical terms from dynamically discovered categories (SPARQL against `https://es.dbpedia.org/sparql`)
- AAS/ECLASS: concept descriptions from the Asset Administration Shell standard, translated EN->ES via `Helsinki-NLP/opus-mt-en-es`
- Local corpus: top-frequency nouns extracted from the active chunk files

Each entry carries: `termino`, `uri`, `source_language`, `surface_es`, `surface_en`, `aliases`.

Cache TTL: 30 days. Refresh manually:

```bash
python src/1_ingestion/termLoader.py --refresh --input data/raw/chunks_manual_instrucciones_a218.txt
```

This file is tracked in version control. It is not regenerated on every pipeline run unless `--refresh` is passed or the cache has expired.
