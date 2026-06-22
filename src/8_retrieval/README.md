# src/8_retrieval

Retrieval, query planning, synthesis, and evaluation over the operational A-Box graph.

## Files

### text_to_sparql.py

Translates natural language queries into SPARQL. Extracts bilingual seed terms (ES/EN), ALL-CAPS identifiers (PLC/CNC codes such as SHUTTERON, LASERON), normalizes them against the multilingual lexicon, and selects a plan family from the catalog.

### multilingual_query_normalizer.py

Normalizes query surfaces for bilingual matching. Applies lemmatization, stop-word removal, and alias expansion using `data/processed/multilingual_lexicon.json`.

### multilingual_lexicon_builder.py

Builds `data/processed/multilingual_lexicon.json` from the operational A-Box. Each entry carries ES/EN surfaces, aliases, and the canonical URI. Run after every A-Box rebuild.

### schema_condenser.py

Produces `data/processed/schema_condensed.txt` — a compact human-readable representation of the T-Box used as context in synthesis prompts. Must be regenerated after any T-Box change.

### synthesis_pipeline.py

Assembles retrieved evidence and generates the final natural language answer using the configured LLM. Applies value normalization rules and surface rendering rules.

### qa_evaluator.py

Formal evaluation entrypoint. Runs a QA dataset against the live graph and reports per-question PASS/FAIL with evidence traces.

```bash
python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_canonical.json
```

### qa_sandbox_diagnostic.py

Diagnostic tool for QA failures. Identifies structural gaps, missing entity clusters, and plan mismatches.

### bilingual_text_canonicalizer.py

Canonicalizes bilingual text surfaces for consistent matching across ES and EN query variants.

## Planner catalogs

The planner selects from pre-built catalogs:

- `data/processed/query_intent_catalog.json` — intent families and their SPARQL templates
- `data/processed/multihop_plan_catalog.json` — multi-hop traversal plans
- `data/processed/planner_generalization_catalog.json` — generalized plan patterns
- `data/processed/boundedness_policy_matrix.json` — boundedness prediction per plan family
