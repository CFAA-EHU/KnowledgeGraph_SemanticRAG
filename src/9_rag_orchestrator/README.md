# src/9_rag_orchestrator

Top-level RAG orchestrator. Coordinates the full retrieval-augmented generation cycle: query normalization, plan selection, SPARQL execution, evidence assembly, and synthesis.

## Files

### semantic_rag.py

Main orchestrator class. Accepts a natural language query, delegates to `text_to_sparql.py` for plan selection, executes the SPARQL against the configured backend, and passes results to `synthesis_pipeline.py` for answer generation.

Called by `query_workbench.py` for interactive use and by `qa_evaluator.py` for batch evaluation.
