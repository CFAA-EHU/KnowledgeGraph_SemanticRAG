# Operational Pipeline Runbook

## Default entrypoint

```bash
python run_operational_pipeline.py --mode resume-compatible
```

## Pilot onboarding for a new English manual

```bash
python run_operational_pipeline.py --source-chunks data/raw/chunks_8070_quick_ref.txt --manual-id 8070_quick_ref --mode resume-compatible
```

This pilot lane writes manual-specific intermediate artifacts first:
- `data/processed/quick_ref_density_report.json`
- `data/processed/quick_ref_language_detection_report.json`
- `data/processed/quick_ref_abox_input.json`
- `data/processed/quick_ref_onboarding_report.json`

If `MISTRAL_API_KEY` is present, the pipeline continues through extraction, merge, canonicalization, enrichment, link completion and lexicon rebuild, publishing into the shared runtime graph.
If `MISTRAL_API_KEY` is missing, the pilot lane must stop before `abox_extractor.py` and leave `quick_ref_integration_decision_report.json` with the blocker explicitly recorded.

## Operational build sequence

1. `src/6_extraction/abox_input_builder.py`
2. `src/6_extraction/abox_extractor.py`
3. `src/6_extraction/abox_merger.py`
4. `src/6_extraction/abox_canonicalizer.py`
5. `src/6_extraction/abox_graph_enricher.py`
6. `src/6_extraction/abox_link_completer.py`
7. `src/8_retrieval/multilingual_lexicon_builder.py`

## Output expectations

After a successful run, the operational lane should contain:
- `data/processed/abox_merged.ttl`
- `data/processed/abox_canonical.ttl`
- `data/processed/abox_enriched.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/multilingual_lexicon.json`
- `data/processed/language_detection_report.json`
- `data/processed/canonical_entity_map.json`
- `data/processed/canonicalization_report.json`
- `data/processed/enrichment_report.json`
- `data/processed/enrichment_link_map.json`
- `data/processed/enrichment_surface_map.json`
- `data/processed/link_completion_report.json`
- `data/processed/link_completion_map.json`
- `data/processed/link_completion_candidates.json`

## Runtime contract

The runtime must load:
- `data/processed/ontology_aligned.ttl`
- `data/processed/abox_linked.ttl`
- `data/processed/multilingual_lexicon.json`

`abox_merged.ttl`, `abox_canonical.ttl` and `abox_enriched.ttl` are diagnostic or intermediate artifacts. They must not be used as the default runtime graph.

`multilingual_lexicon.json` is the bilingual ES/EN lexicalization layer used by planner normalization and answer rendering over the same single graph.

## Post-build validation

Recommended checks after structural changes:
- `python src/8_retrieval/qa_evaluator.py`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_multihop.json`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_bilingual.json`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_8070_quick_ref_bilingual.json`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_8070_quick_ref_bilingual_v2.json --report-path data/processed/quick_ref_v2_eval_report.json --debug-report-path data/processed/quick_ref_v2_debug_report.json`
- `python src/8_retrieval/qa_evaluator.py --qa-file data/golden_set/QA_cross.json --report-path data/processed/cross_eval_report.json --debug-report-path data/processed/cross_debug_report.json`
- `python src/8_retrieval/qa_sandbox_diagnostic.py`

## T21 readiness gates

T21 uses two explicit and separate gates:
- `QA_8070_quick_ref_bilingual_v2.json`: onboarding bilingual readiness of the already integrated quick ref
- `QA_cross.json`: cross-manual semantic integration readiness across A218 + 8070

Do not collapse both into one global score. They measure different risks and must be interpreted independently before writing `data/processed/t21_readiness_decision_report.json`.

## T22 planner hardening gates

T22 keeps the same two gates, but raises them to planner hardening gates with strict convergence targets:
- quick-ref v2:
  - `same_plan_family >= 18/20`
  - `same_sparql_signature >= 18/20`
  - `pair_ok >= 18/20`
  - `answer_language_ok = 20/20`
- cross-manual:
  - `pair_alignment_ok >= 9/11`
  - `cross_case_ok >= 9/11`
  - `answer_language_ok = 11/11`

T22 also writes:
- `data/processed/planner_generalization_catalog_v2.json`
- `data/processed/cross_plan_catalog.json`
- `data/processed/quick_ref_v2_planner_alignment_report.json`
- `data/processed/cross_planner_alignment_report.json`
- `data/processed/t22_planner_eval_report.json`
- `data/processed/t22_planner_decision_report.json`

The planner is considered ready for cleanup and the next manual only if those two gates pass while `QA_canonical` and `QA_multihop` remain stable.
