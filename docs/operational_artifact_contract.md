# Operational Artifact Contract

## Canonical contracts

### Operational lane

- Default build entrypoint: `run_operational_pipeline.py`
- T-Box: `data/processed/ontology_aligned.ttl`
- A-Box input: `data/processed/abox_input.json`
- A-Box manifest: `data/processed/abox_generation_manifest.json`
- A-Box semantic audit: `data/processed/abox_semantic_audit.json`
- A-Box: `data/processed/abox_merged.ttl`

The default operational build runs `abox_input_builder.py`, `abox_extractor.py`, and `abox_merger.py` in that order. The runtime graph contract for this phase remains `ontology_aligned.ttl` plus `abox_merged.ttl`.

### Experimental lane

- Dynamic T-Box prompts: `data/processed/tbox_prompts.json`
- Merged experimental ontology: `data/processed/ontology_merged.ttl`
- Optional aligned A-Box: `data/processed/abox_aligned.ttl`

Experimental artifacts are preserved for iteration and evaluation, but they are not part of the operational runtime contract.

## Script classification

- Operational entrypoint: `run_operational_pipeline.py`
- Operational producer: `src/6_extraction/abox_input_builder.py`
- Operational producer: `src/6_extraction/abox_extractor.py`
- Operational producer: `src/6_extraction/abox_merger.py`
- Operational producer: `src/6_extraction/abox_semantic_validator.py`
- Operational consumer: `src/7_database/embedded_store.py`
- Operational consumer: `src/8_retrieval/schema_condenser.py`
- Operational consumer: `src/8_retrieval/qa_evaluator.py`
- Operational consumer: `src/9_rag_orchestrator/semantic_rag.py`
- Experimental: `src/2_extraction/prompt_assembler.py`
- Experimental: `src/2_extraction/llm_extractor.py`
- Experimental: `src/5_alignment/semantic_reduction.py`

`run_operational_pipeline.py` is the single default build entrypoint. It must orchestrate the operational build only, without touching experimental artifacts.

## Operational build sequence

The canonical operational build sequence is:

1. `src/6_extraction/abox_input_builder.py`
2. `src/6_extraction/abox_extractor.py`
3. `src/6_extraction/abox_merger.py`

The entrypoint must fail explicitly when critical prerequisites are missing, especially the canonical T-Box or `MISTRAL_API_KEY`.

## Operational A-Box input contract

`data/processed/abox_input.json` is the canonical operational input for A-Box extraction.

Each entry contains data payload only, not a rendered prompt:

- `chunk_id`
- `texto_fuente`
- `paginas`
- `seccion`
- `titulo`
- `density_level`
- optional traceability fields such as `terms_found`, `source_path`, `chunk_hash`

`abox_input.json` must be derived from real source text of the manual. It must not contain T-Box instructions, class-generation guidance, or prompt text copied from the experimental lane.

## Compatible resume policy

`data/processed/abox_generation_manifest.json` is the canonical state file for A-Box extraction re-runs.

Each manifest entry records at least:

- `chunk_id`
- `output_path`
- `status`
- `source_text_hash`
- `chunk_hash`
- `tbox_hash`
- `prompt_version`
- `model_name`
- `extraction_mode`
- `last_updated`
- `error_cause` when the chunk ends in `error`
- `semantic_report` when a semantic validation pass was executed

Valid statuses for this phase are:

- `ok`
- `error`
- `missing`
- `stale`

Recognized error causes are intentionally small and diagnostic:

- `rate_limit`
- `timeout`
- `network_error`
- `api_error`
- `ttl_invalid`
- `empty_response`
- `semantic_invalid`

A chunk output is reusable only when all of the following are true:

- the output file exists
- the manifest entry exists
- `status == "ok"`
- `source_text_hash` matches the current `texto_fuente`
- `chunk_hash` matches the current operational chunk payload
- `tbox_hash` matches the canonical T-Box file
- `prompt_version`, `model_name`, and `extraction_mode` all match
- the existing TTL still parses correctly
- the existing TTL still passes semantic validation against the canonical T-Box

If any of those checks fail, the chunk must not be reused blindly.

## Extraction robustness rules

The extractor must only mark a chunk as `ok` after the generated Turtle parses successfully.

Retryable failures such as `rate_limit`, `timeout`, `network_error`, and transient `api_error` receive local retries with bounded backoff before the chunk is left in `error`.

Content failures such as `ttl_invalid`, `empty_response`, and `semantic_invalid` are also retried locally a small number of times, but they are never written as valid outputs and must not reach the merger as reusable chunks.

## Semantic acceptance rules

A Turtle fragment is not operationally acceptable just because it parses. For this phase, an A-Box chunk is semantically acceptable only when all of the following hold:

- it uses only canonical classes from `ontology_aligned.ttl`
- it uses only canonical object and datatype properties from `ontology_aligned.ttl`, plus `rdf:type` and `rdfs:label`
- every described individual has an explicit canonical `rdf:type`
- every extracted individual preserves traceability through `ex:textoExtracto`
- when a chunk contains more than one individual and the text gives a clear relation, the output should contain at least one useful canonical object link

The semantic validator records weak linkage and relation-free outputs as diagnostic signals for this phase, even when they are not the direct cause of rejection.

`data/processed/abox_semantic_audit.json` is the repository-level audit artifact for measuring semantic conformity of the merged operational A-Box.

## Execution modes

The extractor supports three relaunch modes:

- `resume-compatible`: default mode; regenerate only missing, failed, or incompatible chunks
- `force-stale`: regenerate chunks that are not currently reusable under the compatibility contract
- `force-all`: regenerate all chunks regardless of compatibility

The extractor also accepts `--chunk-ids` for controlled semantic re-generation of representative samples without touching the entire corpus.

The operational build entrypoint must propagate one of the three standard resume modes to the extractor.

## Operational boundary

The operational lane must not take `data/processed/tbox_prompts.json` as an input.
Reusing an A-Box chunk because `*_abox.ttl` exists is forbidden by contract.
The default operational build must not use `ontology_merged.ttl` or `abox_aligned.ttl`.
