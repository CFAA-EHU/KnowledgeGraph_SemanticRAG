from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parent
RAW_DATA_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = REPO_ROOT / "data" / "processed"
GOLDEN_SET_DIR = REPO_ROOT / "data" / "golden_set"

OPERATIONAL_TBOX_PATH = PROCESSED_DATA_DIR / "ontology_aligned.ttl"
OPERATIONAL_ABOX_INPUT_PATH = PROCESSED_DATA_DIR / "abox_input.json"
RAW_MERGED_ABOX_PATH = PROCESSED_DATA_DIR / "abox_merged.ttl"
CANONICAL_ABOX_PATH = PROCESSED_DATA_DIR / "abox_canonical.ttl"
ENRICHED_ABOX_PATH = PROCESSED_DATA_DIR / "abox_enriched.ttl"
OPERATIONAL_ABOX_PATH = PROCESSED_DATA_DIR / "abox_linked.ttl"
OPERATIONAL_ABOX_MANIFEST_PATH = PROCESSED_DATA_DIR / "abox_generation_manifest.json"
OPERATIONAL_BUILD_ENTRYPOINT = REPO_ROOT / "run_operational_pipeline.py"
ABOX_SEMANTIC_AUDIT_PATH = PROCESSED_DATA_DIR / "abox_semantic_audit.json"
ABOX_DEBUG_DIR = PROCESSED_DATA_DIR / "abox_debug"

EXPERIMENTAL_TBOX_PROMPTS_PATH = PROCESSED_DATA_DIR / "tbox_prompts.json"
EXPERIMENTAL_TBOX_MERGED_PATH = PROCESSED_DATA_DIR / "ontology_merged.ttl"
EXPERIMENTAL_ABOX_ALIGNED_PATH = PROCESSED_DATA_DIR / "abox_aligned.ttl"

DENSITY_REPORT_PATH = RAW_DATA_DIR / "density_report.json"
EXPERIMENTAL_TBOX_CHUNKS_DIR = PROCESSED_DATA_DIR / "graphs"
ABOX_CHUNKS_DIR = PROCESSED_DATA_DIR / "abox_graphs"
SCHEMA_CONDENSED_PATH = PROCESSED_DATA_DIR / "schema_condensed.txt"
QA2_DATASET_PATH = GOLDEN_SET_DIR / "QA2.txt"
QA3_DATASET_PATH = GOLDEN_SET_DIR / "QA3.json"
QA_CANONICAL_PATH = GOLDEN_SET_DIR / "QA_canonical.json"
QA_SANDBOX_PATH = GOLDEN_SET_DIR / "QA_sandbox.json"
QA_BILINGUAL_PATH = GOLDEN_SET_DIR / "QA_bilingual.json"
QA_8070_QUICK_REF_BILINGUAL_PATH = GOLDEN_SET_DIR / "QA_8070_quick_ref_bilingual.json"
QA_8070_QUICK_REF_BILINGUAL_V2_PATH = GOLDEN_SET_DIR / "QA_8070_quick_ref_bilingual_v2.json"
QA_CROSS_PATH = GOLDEN_SET_DIR / "QA_cross.json"
QA_RECONCILIATION_PATH = PROCESSED_DATA_DIR / "qa_dataset_reconciliation.json"
QA_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "qa_eval_report.json"
QA_FAILURE_ANALYSIS_PATH = PROCESSED_DATA_DIR / "qa_failure_analysis.json"
MULTILINGUAL_LEXICON_PATH = PROCESSED_DATA_DIR / "multilingual_lexicon.json"
LANGUAGE_DETECTION_REPORT_PATH = PROCESSED_DATA_DIR / "language_detection_report.json"
BILINGUAL_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "bilingual_eval_report.json"
BILINGUAL_DEBUG_REPORT_PATH = PROCESSED_DATA_DIR / "bilingual_debug_report.json"
BILINGUAL_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "bilingual_decision_report.json"
QUERY_INTENT_CATALOG_PATH = PROCESSED_DATA_DIR / "query_intent_catalog.json"
QUERY_DEBUG_REPORT_PATH = PROCESSED_DATA_DIR / "query_debug_report.json"
QUERYABILITY_TARGET_MATRIX_PATH = PROCESSED_DATA_DIR / "queryability_target_matrix.json"
ONTOLOGY_QUERYABILITY_AUDIT_PATH = PROCESSED_DATA_DIR / "ontology_queryability_audit.json"
CANONICAL_SPARQL_SUITE_PATH = PROCESSED_DATA_DIR / "canonical_sparql_suite.json"
CANONICAL_SPARQL_EXECUTION_REPORT_PATH = PROCESSED_DATA_DIR / "canonical_sparql_execution_report.json"
CANONICAL_VS_GENERATED_COMPARISON_PATH = PROCESSED_DATA_DIR / "canonical_vs_generated_comparison.json"
QUERYABILITY_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "queryability_decision_report.json"
QA_MULTIHOP_PATH = GOLDEN_SET_DIR / "QA_multihop.json"
MULTIHOP_PLAN_CATALOG_PATH = PROCESSED_DATA_DIR / "multihop_plan_catalog.json"
MULTIHOP_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "multihop_eval_report.json"
MULTIHOP_DEBUG_REPORT_PATH = PROCESSED_DATA_DIR / "multihop_debug_report.json"
MULTIHOP_PLANNER_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "multihop_planner_decision_report.json"
PLANNER_GENERALIZATION_CATALOG_PATH = PROCESSED_DATA_DIR / "planner_generalization_catalog.json"
BOUNDEDNESS_POLICY_MATRIX_PATH = PROCESSED_DATA_DIR / "boundedness_policy_matrix.json"
QUERY_REGRESSION_SET_PATH = PROCESSED_DATA_DIR / "query_regression_set.json"
GENERALIZATION_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "generalization_eval_report.json"
PLANNER_GENERALIZATION_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "planner_generalization_decision_report.json"
SYNTHESIS_ERROR_TAXONOMY_PATH = PROCESSED_DATA_DIR / "synthesis_error_taxonomy.json"
VALUE_NORMALIZATION_RULES_PATH = PROCESSED_DATA_DIR / "value_normalization_rules.json"
SYNTHESIS_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "synthesis_eval_report.json"
SYNTHESIS_DEBUG_REPORT_PATH = PROCESSED_DATA_DIR / "synthesis_debug_report.json"
SYNTHESIS_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "synthesis_decision_report.json"
SURFACE_RENDERING_RULES_PATH = PROCESSED_DATA_DIR / "surface_rendering_rules.json"
SURFACE_POLISH_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "surface_polish_eval_report.json"
SURFACE_POLISH_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "surface_polish_decision_report.json"
SANDBOX_DIAGNOSTIC_REPORT_PATH = PROCESSED_DATA_DIR / "sandbox_diagnostic_report.json"
SANDBOX_STRUCTURAL_GAP_SUMMARY_PATH = PROCESSED_DATA_DIR / "sandbox_structural_gap_summary.json"
SANDBOX_ENTITY_RESOLUTION_CANDIDATES_PATH = PROCESSED_DATA_DIR / "sandbox_entity_resolution_candidates.json"
SANDBOX_PROMOTION_CANDIDATES_PATH = PROCESSED_DATA_DIR / "sandbox_promotion_candidates.json"
SANDBOX_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "sandbox_decision_report.json"
CANONICAL_ENTITY_MAP_PATH = PROCESSED_DATA_DIR / "canonical_entity_map.json"
CANONICALIZATION_REPORT_PATH = PROCESSED_DATA_DIR / "canonicalization_report.json"
CANONICALIZATION_RESOLUTION_CANDIDATES_PATH = PROCESSED_DATA_DIR / "canonicalization_resolution_candidates.json"
CANONICALIZATION_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "canonicalization_eval_report.json"
CANONICALIZATION_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "canonicalization_decision_report.json"
ENRICHMENT_REPORT_PATH = PROCESSED_DATA_DIR / "enrichment_report.json"
ENRICHMENT_LINK_MAP_PATH = PROCESSED_DATA_DIR / "enrichment_link_map.json"
ENRICHMENT_SURFACE_MAP_PATH = PROCESSED_DATA_DIR / "enrichment_surface_map.json"
ENRICHMENT_RESOLUTION_CANDIDATES_PATH = PROCESSED_DATA_DIR / "enrichment_resolution_candidates.json"
ENRICHMENT_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "enrichment_eval_report.json"
ENRICHMENT_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "enrichment_decision_report.json"
LINK_COMPLETION_REPORT_PATH = PROCESSED_DATA_DIR / "link_completion_report.json"
LINK_COMPLETION_MAP_PATH = PROCESSED_DATA_DIR / "link_completion_map.json"
LINK_COMPLETION_CANDIDATES_PATH = PROCESSED_DATA_DIR / "link_completion_candidates.json"
LINK_COMPLETION_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "link_completion_eval_report.json"
LINK_COMPLETION_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "link_completion_decision_report.json"
GRAPHDB_PUBLICATION_REPORT_PATH = PROCESSED_DATA_DIR / "graphdb_publication_report.json"
GRAPHDB_EQUIVALENCE_REPORT_PATH = PROCESSED_DATA_DIR / "graphdb_equivalence_report.json"
T23_GRAPHDB_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "t23_graphdb_decision_report.json"
T24_REPO_INVENTORY_PATH = PROCESSED_DATA_DIR / "t24_repo_inventory.json"
T24_REDUNDANCY_ASSESSMENT_PATH = PROCESSED_DATA_DIR / "t24_redundancy_assessment.json"
T24_CLEANUP_POLICY_PATH = PROCESSED_DATA_DIR / "t24_cleanup_policy.json"
T24_CLEANUP_REPORT_PATH = PROCESSED_DATA_DIR / "t24_cleanup_report.json"
T24_CLEANUP_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "t24_cleanup_decision_report.json"
T25_PENDING_MANUALS_INVENTORY_PATH = PROCESSED_DATA_DIR / "t25_pending_manuals_inventory.json"
T25_MANUAL_ORDER_PATH = PROCESSED_DATA_DIR / "t25_manual_order.json"
T25_MULTI_MANUAL_INTEGRATION_REPORT_PATH = PROCESSED_DATA_DIR / "t25_multi_manual_integration_report.json"
T25_MULTI_MANUAL_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "t25_multi_manual_decision_report.json"
T25_1_8070_INSTALLATION_FAILURE_ANALYSIS_PATH = PROCESSED_DATA_DIR / "t25_1_8070_installation_failure_analysis.json"
T25_1_QR_007_RESIDUAL_ANALYSIS_PATH = PROCESSED_DATA_DIR / "t25_1_qr_007_residual_analysis.json"
T25_1_EXTRACTION_RETRY_POLICY_REPORT_PATH = PROCESSED_DATA_DIR / "t25_1_extraction_retry_policy_report.json"
T25_1_8070_INSTALLATION_RETRY_RUN_REPORT_PATH = PROCESSED_DATA_DIR / "t25_1_8070_installation_retry_run_report.json"
T25_1_QR_007_FIX_REPORT_PATH = PROCESSED_DATA_DIR / "t25_1_qr_007_fix_report.json"
T25_1_RECOVERY_REPORT_PATH = PROCESSED_DATA_DIR / "t25_1_recovery_report.json"
T25_1_RECOVERY_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "t25_1_recovery_decision_report.json"
T25_2_INSTALLATION_CHUNK_INVENTORY_PATH = PROCESSED_DATA_DIR / "t25_2_installation_chunk_inventory.json"
T25_2_INSTALLATION_MANIFEST_AUDIT_PATH = PROCESSED_DATA_DIR / "t25_2_installation_manifest_audit.json"
T25_2_RECOVERY_STRATEGY_REPORT_PATH = PROCESSED_DATA_DIR / "t25_2_recovery_strategy_report.json"
T25_2_INSTALLATION_RECOVERY_EXECUTION_REPORT_PATH = PROCESSED_DATA_DIR / "t25_2_installation_recovery_execution_report.json"
T25_2_RUNTIME_REGENERATION_REPORT_PATH = PROCESSED_DATA_DIR / "t25_2_runtime_regeneration_report.json"
T25_2_GRAPHDB_SYNC_REPORT_PATH = PROCESSED_DATA_DIR / "t25_2_graphdb_sync_report.json"
T25_2_RECOVERY_REPORT_PATH = PROCESSED_DATA_DIR / "t25_2_recovery_report.json"
T25_2_RECOVERY_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "t25_2_recovery_decision_report.json"

GRAPHDB_BASE_URL = os.getenv("GRAPHDB_BASE_URL", "http://localhost:7200").rstrip("/")
GRAPHDB_REPOSITORY_ID = os.getenv("GRAPHDB_REPOSITORY_ID", "semanticrag_operational_mirror")
GRAPHDB_REPOSITORY_URL = f"{GRAPHDB_BASE_URL}/repositories/{GRAPHDB_REPOSITORY_ID}"
GRAPHDB_SPARQL_ENDPOINT = GRAPHDB_REPOSITORY_URL
GRAPHDB_STATEMENTS_ENDPOINT = f"{GRAPHDB_REPOSITORY_URL}/statements"

QUICK_REF_SOURCE_PATH = RAW_DATA_DIR / "chunks_8070_quick_ref.txt"
QUICK_REF_DENSITY_REPORT_PATH = PROCESSED_DATA_DIR / "quick_ref_density_report.json"
QUICK_REF_LANGUAGE_DETECTION_REPORT_PATH = PROCESSED_DATA_DIR / "quick_ref_language_detection_report.json"
QUICK_REF_ABOX_INPUT_PATH = PROCESSED_DATA_DIR / "quick_ref_abox_input.json"
QUICK_REF_ABOX_MANIFEST_PATH = PROCESSED_DATA_DIR / "quick_ref_abox_generation_manifest.json"
QUICK_REF_ABOX_CHUNKS_DIR = PROCESSED_DATA_DIR / "quick_ref_abox_graphs"
QUICK_REF_ABOX_DEBUG_DIR = PROCESSED_DATA_DIR / "quick_ref_abox_debug"
QUICK_REF_RAW_MERGED_ABOX_PATH = PROCESSED_DATA_DIR / "quick_ref_merged.ttl"
QUICK_REF_ONBOARDING_REPORT_PATH = PROCESSED_DATA_DIR / "quick_ref_onboarding_report.json"
QUICK_REF_BILINGUAL_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "quick_ref_bilingual_eval_report.json"
QUICK_REF_BILINGUAL_DEBUG_REPORT_PATH = PROCESSED_DATA_DIR / "quick_ref_bilingual_debug_report.json"
QUICK_REF_INTEGRATION_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "quick_ref_integration_decision_report.json"
QUICK_REF_V2_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "quick_ref_v2_eval_report.json"
QUICK_REF_V2_DEBUG_REPORT_PATH = PROCESSED_DATA_DIR / "quick_ref_v2_debug_report.json"
CROSS_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "cross_eval_report.json"
CROSS_DEBUG_REPORT_PATH = PROCESSED_DATA_DIR / "cross_debug_report.json"
T21_READINESS_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "t21_readiness_decision_report.json"
QUICK_REF_V2_PLANNER_ALIGNMENT_REPORT_PATH = PROCESSED_DATA_DIR / "quick_ref_v2_planner_alignment_report.json"
CROSS_PLANNER_ALIGNMENT_REPORT_PATH = PROCESSED_DATA_DIR / "cross_planner_alignment_report.json"
PLANNER_GENERALIZATION_CATALOG_V2_PATH = PROCESSED_DATA_DIR / "planner_generalization_catalog_v2.json"
CROSS_PLAN_CATALOG_PATH = PROCESSED_DATA_DIR / "cross_plan_catalog.json"
T22_PLANNER_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "t22_planner_eval_report.json"
T22_PLANNER_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "t22_planner_decision_report.json"

ABOX_MAX_LOCAL_RETRIES = 3
ABOX_RETRY_BACKOFF_SECONDS = (5, 15, 30)
ABOX_RETRYABLE_ERROR_CAUSES = {"rate_limit", "timeout", "network_error", "api_error"}
ABOX_CONTENT_ERROR_CAUSES = {"ttl_invalid", "empty_response", "semantic_invalid"}
ABOX_SEMANTIC_WARNING_CATEGORIES = {"weak_linkage", "missing_traceability"}
ABOX_STANDARD_MAX_CONCURRENCY = 2
ABOX_RATE_LIMIT_DRAIN_MAX_CONCURRENCY = 1
ABOX_RATE_LIMIT_DRAIN_MAX_RETRIES = 6
ABOX_RATE_LIMIT_DRAIN_BACKOFF_SECONDS = (15, 30, 60, 120, 240, 480)
ABOX_RATE_LIMIT_DRAIN_JITTER_RANGE = (0.85, 1.15)
ABOX_RATE_LIMIT_DRAIN_REQUEST_SPACING_SECONDS = 2.0
ABOX_MICRO_BATCH_RECOVERY_MAX_CONCURRENCY = 1
ABOX_MICRO_BATCH_RECOVERY_MAX_RETRIES = 6
ABOX_MICRO_BATCH_RECOVERY_BACKOFF_SECONDS = (30, 60, 120, 240, 480, 900)
ABOX_MICRO_BATCH_RECOVERY_JITTER_RANGE = (0.9, 1.1)
ABOX_MICRO_BATCH_RECOVERY_REQUEST_SPACING_SECONDS = 3.0

OPERATIONAL_RUNTIME_CONTRACT = {
    "tbox": OPERATIONAL_TBOX_PATH,
    "abox_input": OPERATIONAL_ABOX_INPUT_PATH,
    "abox_manifest": OPERATIONAL_ABOX_MANIFEST_PATH,
    "abox": OPERATIONAL_ABOX_PATH,
    "abox_merged_raw": RAW_MERGED_ABOX_PATH,
    "abox_canonical": CANONICAL_ABOX_PATH,
    "abox_enriched": ENRICHED_ABOX_PATH,
    "abox_semantic_audit": ABOX_SEMANTIC_AUDIT_PATH,
    "abox_debug": ABOX_DEBUG_DIR,
    "qa_dataset": QA_CANONICAL_PATH,
    "qa_sandbox_dataset": QA_SANDBOX_PATH,
    "qa_bilingual_dataset": QA_BILINGUAL_PATH,
    "qa_8070_quick_ref_bilingual_dataset": QA_8070_QUICK_REF_BILINGUAL_PATH,
    "qa_8070_quick_ref_bilingual_v2_dataset": QA_8070_QUICK_REF_BILINGUAL_V2_PATH,
    "qa_cross_dataset": QA_CROSS_PATH,
    "qa_eval_report": QA_EVAL_REPORT_PATH,
    "qa_failure_analysis": QA_FAILURE_ANALYSIS_PATH,
    "multilingual_lexicon": MULTILINGUAL_LEXICON_PATH,
    "language_detection_report": LANGUAGE_DETECTION_REPORT_PATH,
    "bilingual_eval_report": BILINGUAL_EVAL_REPORT_PATH,
    "bilingual_debug_report": BILINGUAL_DEBUG_REPORT_PATH,
    "bilingual_decision_report": BILINGUAL_DECISION_REPORT_PATH,
    "query_intent_catalog": QUERY_INTENT_CATALOG_PATH,
    "query_debug_report": QUERY_DEBUG_REPORT_PATH,
    "queryability_target_matrix": QUERYABILITY_TARGET_MATRIX_PATH,
    "ontology_queryability_audit": ONTOLOGY_QUERYABILITY_AUDIT_PATH,
    "canonical_sparql_suite": CANONICAL_SPARQL_SUITE_PATH,
    "canonical_sparql_execution_report": CANONICAL_SPARQL_EXECUTION_REPORT_PATH,
    "canonical_vs_generated_comparison": CANONICAL_VS_GENERATED_COMPARISON_PATH,
    "queryability_decision_report": QUERYABILITY_DECISION_REPORT_PATH,
    "qa_multihop": QA_MULTIHOP_PATH,
    "multihop_plan_catalog": MULTIHOP_PLAN_CATALOG_PATH,
    "multihop_eval_report": MULTIHOP_EVAL_REPORT_PATH,
    "multihop_debug_report": MULTIHOP_DEBUG_REPORT_PATH,
    "multihop_planner_decision_report": MULTIHOP_PLANNER_DECISION_REPORT_PATH,
    "planner_generalization_catalog": PLANNER_GENERALIZATION_CATALOG_PATH,
    "boundedness_policy_matrix": BOUNDEDNESS_POLICY_MATRIX_PATH,
    "query_regression_set": QUERY_REGRESSION_SET_PATH,
    "generalization_eval_report": GENERALIZATION_EVAL_REPORT_PATH,
    "planner_generalization_decision_report": PLANNER_GENERALIZATION_DECISION_REPORT_PATH,
    "synthesis_error_taxonomy": SYNTHESIS_ERROR_TAXONOMY_PATH,
    "value_normalization_rules": VALUE_NORMALIZATION_RULES_PATH,
    "synthesis_eval_report": SYNTHESIS_EVAL_REPORT_PATH,
    "synthesis_debug_report": SYNTHESIS_DEBUG_REPORT_PATH,
    "synthesis_decision_report": SYNTHESIS_DECISION_REPORT_PATH,
    "surface_rendering_rules": SURFACE_RENDERING_RULES_PATH,
    "surface_polish_eval_report": SURFACE_POLISH_EVAL_REPORT_PATH,
    "surface_polish_decision_report": SURFACE_POLISH_DECISION_REPORT_PATH,
    "sandbox_diagnostic_report": SANDBOX_DIAGNOSTIC_REPORT_PATH,
    "sandbox_structural_gap_summary": SANDBOX_STRUCTURAL_GAP_SUMMARY_PATH,
    "sandbox_entity_resolution_candidates": SANDBOX_ENTITY_RESOLUTION_CANDIDATES_PATH,
    "sandbox_promotion_candidates": SANDBOX_PROMOTION_CANDIDATES_PATH,
    "sandbox_decision_report": SANDBOX_DECISION_REPORT_PATH,
    "canonical_entity_map": CANONICAL_ENTITY_MAP_PATH,
    "canonicalization_report": CANONICALIZATION_REPORT_PATH,
    "canonicalization_resolution_candidates": CANONICALIZATION_RESOLUTION_CANDIDATES_PATH,
    "canonicalization_eval_report": CANONICALIZATION_EVAL_REPORT_PATH,
    "canonicalization_decision_report": CANONICALIZATION_DECISION_REPORT_PATH,
    "enrichment_report": ENRICHMENT_REPORT_PATH,
    "enrichment_link_map": ENRICHMENT_LINK_MAP_PATH,
    "enrichment_surface_map": ENRICHMENT_SURFACE_MAP_PATH,
    "enrichment_resolution_candidates": ENRICHMENT_RESOLUTION_CANDIDATES_PATH,
    "enrichment_eval_report": ENRICHMENT_EVAL_REPORT_PATH,
    "enrichment_decision_report": ENRICHMENT_DECISION_REPORT_PATH,
    "link_completion_report": LINK_COMPLETION_REPORT_PATH,
    "link_completion_map": LINK_COMPLETION_MAP_PATH,
    "link_completion_candidates": LINK_COMPLETION_CANDIDATES_PATH,
    "link_completion_eval_report": LINK_COMPLETION_EVAL_REPORT_PATH,
    "link_completion_decision_report": LINK_COMPLETION_DECISION_REPORT_PATH,
    "graphdb_base_url": GRAPHDB_BASE_URL,
    "graphdb_repository_id": GRAPHDB_REPOSITORY_ID,
    "graphdb_repository_url": GRAPHDB_REPOSITORY_URL,
    "graphdb_sparql_endpoint": GRAPHDB_SPARQL_ENDPOINT,
    "graphdb_statements_endpoint": GRAPHDB_STATEMENTS_ENDPOINT,
    "graphdb_publication_report": GRAPHDB_PUBLICATION_REPORT_PATH,
    "graphdb_equivalence_report": GRAPHDB_EQUIVALENCE_REPORT_PATH,
    "t23_graphdb_decision_report": T23_GRAPHDB_DECISION_REPORT_PATH,
    "t24_repo_inventory": T24_REPO_INVENTORY_PATH,
    "t24_redundancy_assessment": T24_REDUNDANCY_ASSESSMENT_PATH,
    "t24_cleanup_policy": T24_CLEANUP_POLICY_PATH,
    "t24_cleanup_report": T24_CLEANUP_REPORT_PATH,
    "t24_cleanup_decision_report": T24_CLEANUP_DECISION_REPORT_PATH,
    "t25_pending_manuals_inventory": T25_PENDING_MANUALS_INVENTORY_PATH,
    "t25_manual_order": T25_MANUAL_ORDER_PATH,
    "t25_multi_manual_integration_report": T25_MULTI_MANUAL_INTEGRATION_REPORT_PATH,
    "t25_multi_manual_decision_report": T25_MULTI_MANUAL_DECISION_REPORT_PATH,
    "t25_1_8070_installation_failure_analysis": T25_1_8070_INSTALLATION_FAILURE_ANALYSIS_PATH,
    "t25_1_qr_007_residual_analysis": T25_1_QR_007_RESIDUAL_ANALYSIS_PATH,
    "t25_1_extraction_retry_policy_report": T25_1_EXTRACTION_RETRY_POLICY_REPORT_PATH,
    "t25_1_8070_installation_retry_run_report": T25_1_8070_INSTALLATION_RETRY_RUN_REPORT_PATH,
    "t25_1_qr_007_fix_report": T25_1_QR_007_FIX_REPORT_PATH,
    "t25_1_recovery_report": T25_1_RECOVERY_REPORT_PATH,
    "t25_1_recovery_decision_report": T25_1_RECOVERY_DECISION_REPORT_PATH,
    "t25_2_installation_chunk_inventory": T25_2_INSTALLATION_CHUNK_INVENTORY_PATH,
    "t25_2_installation_manifest_audit": T25_2_INSTALLATION_MANIFEST_AUDIT_PATH,
    "t25_2_recovery_strategy_report": T25_2_RECOVERY_STRATEGY_REPORT_PATH,
    "t25_2_installation_recovery_execution_report": T25_2_INSTALLATION_RECOVERY_EXECUTION_REPORT_PATH,
    "t25_2_runtime_regeneration_report": T25_2_RUNTIME_REGENERATION_REPORT_PATH,
    "t25_2_graphdb_sync_report": T25_2_GRAPHDB_SYNC_REPORT_PATH,
    "t25_2_recovery_report": T25_2_RECOVERY_REPORT_PATH,
    "t25_2_recovery_decision_report": T25_2_RECOVERY_DECISION_REPORT_PATH,
    "quick_ref_source": QUICK_REF_SOURCE_PATH,
    "quick_ref_density_report": QUICK_REF_DENSITY_REPORT_PATH,
    "quick_ref_language_detection_report": QUICK_REF_LANGUAGE_DETECTION_REPORT_PATH,
    "quick_ref_abox_input": QUICK_REF_ABOX_INPUT_PATH,
    "quick_ref_abox_manifest": QUICK_REF_ABOX_MANIFEST_PATH,
    "quick_ref_abox_chunks_dir": QUICK_REF_ABOX_CHUNKS_DIR,
    "quick_ref_abox_debug_dir": QUICK_REF_ABOX_DEBUG_DIR,
    "quick_ref_merged": QUICK_REF_RAW_MERGED_ABOX_PATH,
    "quick_ref_onboarding_report": QUICK_REF_ONBOARDING_REPORT_PATH,
    "quick_ref_bilingual_eval_report": QUICK_REF_BILINGUAL_EVAL_REPORT_PATH,
    "quick_ref_bilingual_debug_report": QUICK_REF_BILINGUAL_DEBUG_REPORT_PATH,
    "quick_ref_integration_decision_report": QUICK_REF_INTEGRATION_DECISION_REPORT_PATH,
    "quick_ref_v2_eval_report": QUICK_REF_V2_EVAL_REPORT_PATH,
    "quick_ref_v2_debug_report": QUICK_REF_V2_DEBUG_REPORT_PATH,
    "cross_eval_report": CROSS_EVAL_REPORT_PATH,
    "cross_debug_report": CROSS_DEBUG_REPORT_PATH,
    "t21_readiness_decision_report": T21_READINESS_DECISION_REPORT_PATH,
    "quick_ref_v2_planner_alignment_report": QUICK_REF_V2_PLANNER_ALIGNMENT_REPORT_PATH,
    "cross_planner_alignment_report": CROSS_PLANNER_ALIGNMENT_REPORT_PATH,
    "planner_generalization_catalog_v2": PLANNER_GENERALIZATION_CATALOG_V2_PATH,
    "cross_plan_catalog": CROSS_PLAN_CATALOG_PATH,
    "t22_planner_eval_report": T22_PLANNER_EVAL_REPORT_PATH,
    "t22_planner_decision_report": T22_PLANNER_DECISION_REPORT_PATH,
}

OPERATIONAL_BUILD_PIPELINE = {
    "entrypoint": OPERATIONAL_BUILD_ENTRYPOINT,
    "stages": [
        REPO_ROOT / "src" / "6_extraction" / "abox_input_builder.py",
        REPO_ROOT / "src" / "6_extraction" / "abox_extractor.py",
        REPO_ROOT / "src" / "6_extraction" / "abox_merger.py",
        REPO_ROOT / "src" / "6_extraction" / "abox_canonicalizer.py",
        REPO_ROOT / "src" / "6_extraction" / "abox_graph_enricher.py",
        REPO_ROOT / "src" / "6_extraction" / "abox_link_completer.py",
        REPO_ROOT / "src" / "8_retrieval" / "multilingual_lexicon_builder.py",
    ],
}

EXPERIMENTAL_ARTIFACT_CONTRACT = {
    "dynamic_tbox_prompts": EXPERIMENTAL_TBOX_PROMPTS_PATH,
    "ontology_merged": EXPERIMENTAL_TBOX_MERGED_PATH,
    "abox_aligned_optional": EXPERIMENTAL_ABOX_ALIGNED_PATH,
}

PROHIBITED_OPERATIONAL_INPUTS = {
    EXPERIMENTAL_TBOX_PROMPTS_PATH,
}

SCRIPT_CLASSIFICATIONS = {
    "run_operational_pipeline.py": "operational_entrypoint",
    "src/2_extraction/prompt_assembler.py": "experimental",
    "src/2_extraction/llm_extractor.py": "experimental",
    "src/5_alignment/semantic_reduction.py": "experimental",
    "src/6_extraction/abox_input_builder.py": "operational_producer",
    "src/6_extraction/abox_extractor.py": "operational_producer",
    "src/6_extraction/abox_merger.py": "operational_producer",
    "src/6_extraction/abox_canonicalizer.py": "operational_producer",
    "src/6_extraction/abox_graph_enricher.py": "operational_producer",
    "src/6_extraction/abox_link_completer.py": "operational_producer",
    "src/6_extraction/abox_semantic_validator.py": "operational_producer",
    "src/8_retrieval/multilingual_lexicon_builder.py": "operational_producer",
    "src/7_database/embedded_store.py": "operational_consumer",
    "src/7_database/graphdb_client.py": "operational_consumer",
    "src/7_database/graph_store.py": "operational_consumer",
    "src/7_database/publish_to_graphdb.py": "operational_consumer",
    "src/7_database/graphdb_healthcheck.py": "operational_consumer",
    "src/8_retrieval/schema_condenser.py": "operational_consumer",
    "src/8_retrieval/qa_evaluator.py": "operational_consumer",
    "src/9_rag_orchestrator/semantic_rag.py": "operational_consumer",
    "run_t25_sequential_integration.py": "operational_entrypoint",
}


@dataclass(frozen=True)
class AboxReuseSignature:
    source_text_hash: str
    chunk_hash: str
    tbox_hash: str
    prompt_version: str
    model_name: str
    extraction_mode: str


@dataclass(frozen=True)
class OnboardingArtifactProfile:
    manual_id: str
    artifact_prefix: str
    source_path: Path
    density_report_path: Path
    language_detection_report_path: Path
    abox_input_path: Path
    abox_manifest_path: Path
    abox_chunks_dir: Path
    abox_debug_dir: Path
    raw_merged_abox_path: Path
    onboarding_report_path: Path
    bilingual_dataset_path: Path | None = None
    bilingual_eval_report_path: Path | None = None
    bilingual_debug_report_path: Path | None = None
    integration_decision_report_path: Path | None = None


def derive_onboarding_artifact_prefix(source_path: Path, manual_id: str) -> str:
    stem = source_path.stem.lower()
    stem = re.sub(r"^chunks_", "", stem)
    stem = re.sub(r"^\d+_", "", stem)
    stem = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    if stem:
        return stem
    fallback = re.sub(r"[^a-z0-9]+", "_", manual_id.lower()).strip("_")
    return fallback or "manual"


def build_onboarding_profile(manual_id: str, source_path: Path) -> OnboardingArtifactProfile:
    if source_path.resolve() == QUICK_REF_SOURCE_PATH.resolve():
        return OnboardingArtifactProfile(
            manual_id=manual_id,
            artifact_prefix="quick_ref",
            source_path=source_path,
            density_report_path=QUICK_REF_DENSITY_REPORT_PATH,
            language_detection_report_path=QUICK_REF_LANGUAGE_DETECTION_REPORT_PATH,
            abox_input_path=QUICK_REF_ABOX_INPUT_PATH,
            abox_manifest_path=QUICK_REF_ABOX_MANIFEST_PATH,
            abox_chunks_dir=QUICK_REF_ABOX_CHUNKS_DIR,
            abox_debug_dir=QUICK_REF_ABOX_DEBUG_DIR,
            raw_merged_abox_path=QUICK_REF_RAW_MERGED_ABOX_PATH,
            onboarding_report_path=QUICK_REF_ONBOARDING_REPORT_PATH,
            bilingual_dataset_path=QA_8070_QUICK_REF_BILINGUAL_PATH,
            bilingual_eval_report_path=QUICK_REF_BILINGUAL_EVAL_REPORT_PATH,
            bilingual_debug_report_path=QUICK_REF_BILINGUAL_DEBUG_REPORT_PATH,
            integration_decision_report_path=QUICK_REF_INTEGRATION_DECISION_REPORT_PATH,
        )

    prefix = derive_onboarding_artifact_prefix(source_path, manual_id)
    return OnboardingArtifactProfile(
        manual_id=manual_id,
        artifact_prefix=prefix,
        source_path=source_path,
        density_report_path=PROCESSED_DATA_DIR / f"{prefix}_density_report.json",
        language_detection_report_path=PROCESSED_DATA_DIR / f"{prefix}_language_detection_report.json",
        abox_input_path=PROCESSED_DATA_DIR / f"{prefix}_abox_input.json",
        abox_manifest_path=PROCESSED_DATA_DIR / f"{prefix}_abox_generation_manifest.json",
        abox_chunks_dir=PROCESSED_DATA_DIR / f"{prefix}_abox_graphs",
        abox_debug_dir=PROCESSED_DATA_DIR / f"{prefix}_abox_debug",
        raw_merged_abox_path=PROCESSED_DATA_DIR / f"{prefix}_merged.ttl",
        onboarding_report_path=PROCESSED_DATA_DIR / f"{prefix}_onboarding_report.json",
        bilingual_eval_report_path=PROCESSED_DATA_DIR / f"{prefix}_bilingual_eval_report.json",
        bilingual_debug_report_path=PROCESSED_DATA_DIR / f"{prefix}_bilingual_debug_report.json",
        integration_decision_report_path=PROCESSED_DATA_DIR / f"{prefix}_integration_decision_report.json",
    )


def hash_text_content(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def hash_json_content(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def hash_file_content(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def build_abox_chunk_hash(chunk_data: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in chunk_data.items() if key != "chunk_hash"}
    return hash_json_content(payload)


def build_abox_reuse_signature(
    source_text: str,
    *,
    chunk_data: Mapping[str, Any],
    prompt_version: str,
    model_name: str,
    extraction_mode: str,
    tbox_hash: str | None = None,
    tbox_path: Path = OPERATIONAL_TBOX_PATH,
) -> AboxReuseSignature:
    resolved_tbox_hash = tbox_hash or hash_file_content(tbox_path)
    return AboxReuseSignature(
        source_text_hash=hash_text_content(source_text),
        chunk_hash=build_abox_chunk_hash(chunk_data),
        tbox_hash=resolved_tbox_hash,
        prompt_version=prompt_version,
        model_name=model_name,
        extraction_mode=extraction_mode,
    )


def abox_reuse_signature_dict(signature: AboxReuseSignature) -> dict[str, str]:
    return asdict(signature)


def is_reusable_abox_output(
    persisted_metadata: Mapping[str, Any] | None,
    *,
    source_text: str,
    chunk_data: Mapping[str, Any],
    prompt_version: str,
    model_name: str,
    extraction_mode: str,
    tbox_hash: str | None = None,
    tbox_path: Path = OPERATIONAL_TBOX_PATH,
) -> bool:
    if not persisted_metadata:
        return False

    expected = build_abox_reuse_signature(
        source_text,
        chunk_data=chunk_data,
        prompt_version=prompt_version,
        model_name=model_name,
        extraction_mode=extraction_mode,
        tbox_hash=tbox_hash,
        tbox_path=tbox_path,
    )

    return persisted_metadata == abox_reuse_signature_dict(expected)
