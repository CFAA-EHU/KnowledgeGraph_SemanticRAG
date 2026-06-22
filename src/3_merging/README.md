# src/3_merging

Experimental T-Box graph merger. Not part of the default operational runtime.

## Files

- `graph_merger.py` — merges per-chunk TTL fragments from `data/processed/graphs/` into a single `data/processed/ontology_merged.ttl`. Run with `python src/3_merging/graph_merger.py`.

## Status

Retained for experimental use. The operational merger for A-Box graphs is `src/6_extraction/abox_merger.py`.
