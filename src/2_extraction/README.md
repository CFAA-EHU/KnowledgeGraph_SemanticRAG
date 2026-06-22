# src/2_extraction

Experimental T-Box extractor using MistralAI. Not part of the default operational runtime.

## Files

- `llm_extractor.py` — async extractor that sends chunk prompts to the Mistral API and parses Turtle responses. Requires `MISTRAL_API_KEY` environment variable.
- `prompt_assembler.py` — assembles prompts for T-Box extraction from chunk data.

## Status

This lane is retained for experimental use only. The operational A-Box extraction pipeline is in `src/6_extraction/`. T-Box prompts and merged ontology outputs from this lane (`data/processed/tbox_prompts.json`, `data/processed/ontology_merged.ttl`) are classified as experimental artifacts and are not consumed by the runtime.
