from __future__ import annotations

import json
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
OPERATIONAL_ABOX_PATH = PROCESSED_DATA_DIR / "abox_merged.ttl"
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
QA_RECONCILIATION_PATH = PROCESSED_DATA_DIR / "qa_dataset_reconciliation.json"
QA_EVAL_REPORT_PATH = PROCESSED_DATA_DIR / "qa_eval_report.json"
QA_FAILURE_ANALYSIS_PATH = PROCESSED_DATA_DIR / "qa_failure_analysis.json"
QUERY_INTENT_CATALOG_PATH = PROCESSED_DATA_DIR / "query_intent_catalog.json"
QUERY_DEBUG_REPORT_PATH = PROCESSED_DATA_DIR / "query_debug_report.json"
QUERYABILITY_TARGET_MATRIX_PATH = PROCESSED_DATA_DIR / "queryability_target_matrix.json"
ONTOLOGY_QUERYABILITY_AUDIT_PATH = PROCESSED_DATA_DIR / "ontology_queryability_audit.json"
CANONICAL_SPARQL_SUITE_PATH = PROCESSED_DATA_DIR / "canonical_sparql_suite.json"
CANONICAL_SPARQL_EXECUTION_REPORT_PATH = PROCESSED_DATA_DIR / "canonical_sparql_execution_report.json"
CANONICAL_VS_GENERATED_COMPARISON_PATH = PROCESSED_DATA_DIR / "canonical_vs_generated_comparison.json"
QUERYABILITY_DECISION_REPORT_PATH = PROCESSED_DATA_DIR / "queryability_decision_report.json"
QA_MULTIHOP_PATH = GOLDEN_SET_DIR / "QA_multihop.json"

ABOX_MAX_LOCAL_RETRIES = 3
ABOX_RETRY_BACKOFF_SECONDS = (5, 15, 30)
ABOX_RETRYABLE_ERROR_CAUSES = {"rate_limit", "timeout", "network_error", "api_error"}
ABOX_CONTENT_ERROR_CAUSES = {"ttl_invalid", "empty_response", "semantic_invalid"}
ABOX_SEMANTIC_WARNING_CATEGORIES = {"weak_linkage", "missing_traceability"}

OPERATIONAL_RUNTIME_CONTRACT = {
    "tbox": OPERATIONAL_TBOX_PATH,
    "abox_input": OPERATIONAL_ABOX_INPUT_PATH,
    "abox_manifest": OPERATIONAL_ABOX_MANIFEST_PATH,
    "abox": OPERATIONAL_ABOX_PATH,
    "abox_semantic_audit": ABOX_SEMANTIC_AUDIT_PATH,
    "abox_debug": ABOX_DEBUG_DIR,
    "qa_dataset": QA_CANONICAL_PATH,
    "qa_eval_report": QA_EVAL_REPORT_PATH,
    "qa_failure_analysis": QA_FAILURE_ANALYSIS_PATH,
    "query_intent_catalog": QUERY_INTENT_CATALOG_PATH,
    "query_debug_report": QUERY_DEBUG_REPORT_PATH,
    "queryability_target_matrix": QUERYABILITY_TARGET_MATRIX_PATH,
    "ontology_queryability_audit": ONTOLOGY_QUERYABILITY_AUDIT_PATH,
    "canonical_sparql_suite": CANONICAL_SPARQL_SUITE_PATH,
    "canonical_sparql_execution_report": CANONICAL_SPARQL_EXECUTION_REPORT_PATH,
    "canonical_vs_generated_comparison": CANONICAL_VS_GENERATED_COMPARISON_PATH,
    "queryability_decision_report": QUERYABILITY_DECISION_REPORT_PATH,
    "qa_multihop": QA_MULTIHOP_PATH,
}

OPERATIONAL_BUILD_PIPELINE = {
    "entrypoint": OPERATIONAL_BUILD_ENTRYPOINT,
    "stages": [
        REPO_ROOT / "src" / "6_extraction" / "abox_input_builder.py",
        REPO_ROOT / "src" / "6_extraction" / "abox_extractor.py",
        REPO_ROOT / "src" / "6_extraction" / "abox_merger.py",
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
    "src/6_extraction/abox_semantic_validator.py": "operational_producer",
    "src/7_database/embedded_store.py": "operational_consumer",
    "src/8_retrieval/schema_condenser.py": "operational_consumer",
    "src/8_retrieval/qa_evaluator.py": "operational_consumer",
    "src/9_rag_orchestrator/semantic_rag.py": "operational_consumer",
}


@dataclass(frozen=True)
class AboxReuseSignature:
    source_text_hash: str
    chunk_hash: str
    tbox_hash: str
    prompt_version: str
    model_name: str
    extraction_mode: str


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
