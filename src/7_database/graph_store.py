from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CURRENT_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from rdflib import Graph

from artifact_contracts import (
    GRAPHDB_EQUIVALENCE_REPORT_PATH,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
)
from graphdb_client import GraphDBClient, build_graphdb_client


class BaseGraphStore(ABC):
    """Minimal backend interface for direct SPARQL execution over the operational graph."""

    @abstractmethod
    def backend_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def select(self, query: str) -> list[dict[str, str]]:
        raise NotImplementedError

    @abstractmethod
    def ask(self, query: str) -> bool:
        raise NotImplementedError

    def is_remote(self) -> bool:
        return False

    def raw_graph(self) -> Graph | None:
        return None


class RDFLibGraphStore(BaseGraphStore):
    def __init__(self, *, tbox_path: Path = OPERATIONAL_TBOX_PATH, abox_path: Path = OPERATIONAL_ABOX_PATH) -> None:
        self._graph = Graph()
        self._graph.parse(tbox_path, format="turtle")
        self._graph.parse(abox_path, format="turtle")

    def backend_name(self) -> str:
        return "rdflib"

    def select(self, query: str) -> list[dict[str, str]]:
        result = self._graph.query(query)
        variables = [str(variable) for variable in result.vars]
        rows: list[dict[str, str]] = []
        for row in result:
            rows.append({name: str(value) for name, value in zip(variables, row)})
        return rows

    def ask(self, query: str) -> bool:
        result = self._graph.query(query)
        return bool(getattr(result, "askAnswer", False))

    def raw_graph(self) -> Graph:
        return self._graph


class GraphDBGraphStore(BaseGraphStore):
    def __init__(self, client: GraphDBClient | None = None) -> None:
        self.client = client or build_graphdb_client()

    def backend_name(self) -> str:
        return "graphdb"

    def select(self, query: str) -> list[dict[str, str]]:
        return self.client.run_select(query)

    def ask(self, query: str) -> bool:
        return self.client.run_ask(query)

    def query(self, query: str) -> list[tuple[str, ...]]:
        payload = self.client.run_select_raw(query)
        variables = payload.get("head", {}).get("vars", [])
        rows: list[tuple[str, ...]] = []
        for binding in payload.get("results", {}).get("bindings", []):
            rows.append(tuple(binding.get(variable, {}).get("value", "") for variable in variables))
        return rows

    def is_remote(self) -> bool:
        return True


def build_graph_store(backend: str = "rdflib") -> BaseGraphStore:
    normalized = backend.strip().lower()
    if normalized == "graphdb":
        return GraphDBGraphStore()
    return RDFLibGraphStore()


EQUIVALENCE_CASES = [
    {
        "case_id": "a218_directive",
        "query_id": "directive_machine",
        "sparql": """
PREFIX ex: <https://vocab.cfaa.eus/broaching/>
SELECT DISTINCT ?directive WHERE {
  ex:MaquinaBrochadoExterior_18 ex:cumpleNormativa ?directive .
}
ORDER BY ?directive
""".strip(),
    },
    {
        "case_id": "ekin_email",
        "query_id": "company_email",
        "sparql": """
PREFIX ex: <https://vocab.cfaa.eus/broaching/>
SELECT DISTINCT ?company ?text WHERE {
  ?company ex:textoExtracto ?text .
  FILTER(CONTAINS(LCASE(STR(?text)), "ekin@ekin.es"))
}
ORDER BY ?company ?text
""".strip(),
    },
    {
        "case_id": "known_figure",
        "query_id": "figure_lookup",
        "sparql": """
PREFIX ex: <https://vocab.cfaa.eus/broaching/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?figure WHERE {
  ?figure rdfs:label "Figura 6-1"@es .
}
""".strip(),
    },
    {
        "case_id": "hydraulic_oil",
        "query_id": "oil_lookup",
        "sparql": """
PREFIX ex: <https://vocab.cfaa.eus/broaching/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?item WHERE {
  ?item rdfs:label ?label .
  FILTER(CONTAINS(LCASE(STR(?label)), "aceite"))
}
ORDER BY ?item
LIMIT 10
""".strip(),
    },
    {
        "case_id": "quick_ref_focus",
        "query_id": "quick_ref_focus",
        "sparql": """
PREFIX ex: <https://vocab.cfaa.eus/broaching/>
SELECT DISTINCT ?key ?text WHERE {
  ?key ex:textoExtracto ?text .
  FILTER(CONTAINS(LCASE(STR(?text)), "focus"))
}
ORDER BY ?key ?text
LIMIT 10
""".strip(),
    },
    {
        "case_id": "cross_c_axis",
        "query_id": "cross_c_axis",
        "sparql": """
PREFIX ex: <https://vocab.cfaa.eus/broaching/>
SELECT DISTINCT ?item ?text WHERE {
  ?item ex:textoExtracto ?text .
  FILTER(CONTAINS(LCASE(STR(?text)), "#cax"))
}
ORDER BY ?item ?text
LIMIT 10
""".strip(),
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key_entities(rows: list[dict[str, str]]) -> list[str]:
    values: list[str] = []
    for row in rows:
        for value in row.values():
            if value and value not in values:
                values.append(value)
    return values[:10]


def _equivalence_status(rdflib_rows: list[dict[str, str]], graphdb_rows: list[dict[str, str]]) -> str:
    if not rdflib_rows and not graphdb_rows:
        return "equivalent"
    rdflib_entities = set(_key_entities(rdflib_rows))
    graphdb_entities = set(_key_entities(graphdb_rows))
    if rdflib_entities == graphdb_entities and rdflib_entities:
        return "equivalent"
    if rdflib_entities.intersection(graphdb_entities):
        return "partially_equivalent"
    return "failed"


def build_graphdb_equivalence_report(output_path: Path = GRAPHDB_EQUIVALENCE_REPORT_PATH) -> dict[str, Any]:
    # This runner only checks basic backend equivalence for stable SPARQL cases.
    # It is intentionally separate from planner, retrieval and synthesis logic.
    rdflib_store = RDFLibGraphStore()
    graphdb_store = GraphDBGraphStore()
    results = []
    for case in EQUIVALENCE_CASES:
        rdflib_status = "ok"
        graphdb_status = "ok"
        rdflib_rows: list[dict[str, str]] = []
        graphdb_rows: list[dict[str, str]] = []
        notes: list[str] = []
        try:
            rdflib_rows = rdflib_store.select(case["sparql"])
        except Exception as exc:  # pragma: no cover - runtime integration
            rdflib_status = f"error:{exc}"
        try:
            graphdb_rows = graphdb_store.select(case["sparql"])
        except Exception as exc:  # pragma: no cover - runtime integration
            graphdb_status = f"error:{exc}"
        status = _equivalence_status(rdflib_rows, graphdb_rows)
        if rdflib_status != "ok" or graphdb_status != "ok":
            status = "failed"
        if rdflib_rows and not graphdb_rows:
            notes.append("GraphDB returned no rows while RDFLib did.")
        elif graphdb_rows and not rdflib_rows:
            notes.append("GraphDB returned rows while RDFLib did not.")
        elif status == "partially_equivalent":
            notes.append("Shared key entities overlap but are not identical.")
        results.append(
            {
                "case_id": case["case_id"],
                "query_id": case["query_id"],
                "sparql": case["sparql"],
                "rdflib_status": rdflib_status,
                "graphdb_status": graphdb_status,
                "rdflib_key_entities": _key_entities(rdflib_rows),
                "graphdb_key_entities": _key_entities(graphdb_rows),
                "equivalence_status": status,
                "notes": notes,
            }
        )

    summary = {
        "timestamp": _utc_now(),
        "total_cases": len(results),
        "equivalent_cases": sum(1 for item in results if item["equivalence_status"] == "equivalent"),
        "partial_cases": sum(1 for item in results if item["equivalence_status"] == "partially_equivalent"),
        "failed_cases": sum(1 for item in results if item["equivalence_status"] == "failed"),
    }
    report = {"summary": summary, "results": results}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    report = build_graphdb_equivalence_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["summary"]["failed_cases"] > 0:
        raise SystemExit(1)


__all__ = [
    "BaseGraphStore",
    "RDFLibGraphStore",
    "GraphDBGraphStore",
    "build_graph_store",
    "build_graphdb_equivalence_report",
]


if __name__ == "__main__":
    main()
