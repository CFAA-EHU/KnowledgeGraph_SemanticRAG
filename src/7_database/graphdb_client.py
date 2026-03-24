from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from artifact_contracts import (
    GRAPHDB_BASE_URL,
    GRAPHDB_REPOSITORY_ID,
    GRAPHDB_REPOSITORY_URL,
    GRAPHDB_SPARQL_ENDPOINT,
    GRAPHDB_STATEMENTS_ENDPOINT,
)


class GraphDBClientError(RuntimeError):
    pass


class GraphDBClient:
    def __init__(
        self,
        *,
        base_url: str = GRAPHDB_BASE_URL,
        repository_id: str = GRAPHDB_REPOSITORY_ID,
        timeout_seconds: int = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.repository_id = repository_id
        self.repository_url = f"{self.base_url}/repositories/{self.repository_id}"
        self.sparql_endpoint = self.repository_url
        self.statements_endpoint = f"{self.repository_url}/statements"
        self.rest_repositories_endpoint = f"{self.base_url}/rest/repositories"
        self.timeout_seconds = timeout_seconds

    def _raise_for_status(self, response: requests.Response, message: str) -> None:
        if response.ok:
            return
        body = response.text.strip()
        detail = f"{message}: HTTP {response.status_code}"
        if body:
            detail = f"{detail} - {body[:500]}"
        raise GraphDBClientError(detail)

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        try:
            response = requests.request(method, url, timeout=self.timeout_seconds, **kwargs)
        except requests.RequestException as exc:
            raise GraphDBClientError(str(exc)) from exc
        return response

    def healthcheck(self) -> dict[str, Any]:
        response = self._request("GET", self.rest_repositories_endpoint, headers={"Accept": "application/json"})
        self._raise_for_status(response, "GraphDB healthcheck failed")
        repositories = response.json() if response.text.strip() else []
        return {
            "server_available": True,
            "base_url": self.base_url,
            "repository_count": len(repositories) if isinstance(repositories, list) else None,
        }

    def repository_exists(self) -> bool:
        response = self._request("GET", self.rest_repositories_endpoint, headers={"Accept": "application/json"})
        self._raise_for_status(response, "Could not list GraphDB repositories")
        payload = response.json() if response.text.strip() else []
        if not isinstance(payload, list):
            return False
        return any(str(item.get("id", "")) == self.repository_id for item in payload if isinstance(item, dict))

    def create_repository(self) -> dict[str, Any]:
        config = self._repository_config()
        files = {
            "config": ("repo-config.ttl", config.encode("utf-8"), "text/turtle"),
        }
        response = self._request("POST", self.rest_repositories_endpoint, files=files)
        self._raise_for_status(response, f"Could not create GraphDB repository {self.repository_id}")
        return {"repository_id": self.repository_id, "created": True}

    def clear_repository(self) -> None:
        response = self._request("DELETE", self.statements_endpoint)
        self._raise_for_status(response, f"Could not clear GraphDB repository {self.repository_id}")

    def upload_turtle_file(self, file_path: str | Path, context: str | None = None) -> dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            raise GraphDBClientError(f"Turtle file not found: {path}")
        params = {}
        if context:
            params["context"] = f"<{context}>"
        response = self._request(
            "POST",
            self.statements_endpoint,
            params=params,
            headers={"Content-Type": "text/turtle"},
            data=path.read_bytes(),
        )
        self._raise_for_status(response, f"Could not upload Turtle file {path}")
        return {"file_path": str(path), "context": context, "status": "uploaded"}

    def run_select(self, query: str) -> list[dict[str, str]]:
        payload = self.run_select_raw(query)
        bindings = payload.get("results", {}).get("bindings", [])
        rows: list[dict[str, str]] = []
        for binding in bindings:
            row = {
                key: value.get("value", "")
                for key, value in binding.items()
                if isinstance(value, dict)
            }
            rows.append(row)
        return rows

    def run_select_raw(self, query: str) -> dict[str, Any]:
        response = self._request(
            "POST",
            self.sparql_endpoint,
            headers={"Accept": "application/sparql-results+json"},
            data={"query": query},
        )
        self._raise_for_status(response, "GraphDB SELECT query failed")
        return response.json()

    def run_ask(self, query: str) -> bool:
        response = self._request(
            "POST",
            self.sparql_endpoint,
            headers={"Accept": "application/sparql-results+json"},
            data={"query": query},
        )
        self._raise_for_status(response, "GraphDB ASK query failed")
        payload = response.json()
        return bool(payload.get("boolean", False))

    def _repository_config(self) -> str:
        return f"""@prefix rep: <http://www.openrdf.org/config/repository#> .
@prefix sr: <http://www.openrdf.org/config/repository/sail#> .
@prefix sail: <http://www.openrdf.org/config/sail#> .
@prefix graphdb: <http://www.ontotext.com/config/graphdb#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

[] a rep:Repository ;
   rep:repositoryID "{self.repository_id}" ;
   rdfs:label "{self.repository_id}" ;
   rep:repositoryImpl [
     rep:repositoryType "graphdb:SailRepository" ;
     sr:sailImpl [
       sail:sailType "graphdb:Sail" ;
       graphdb:entity-id-size "32" ;
       graphdb:base-URL "http://semanticrag.local/entity/" ;
       graphdb:defaultNS "https://vocab.cfaa.eus/broaching/" ;
       graphdb:enable-context-index "true" ;
       graphdb:enablePredicateList "true" ;
       graphdb:in-memory-literal-properties "true" ;
       graphdb:enable-literal-index "true" ;
       graphdb:check-for-inconsistencies "false" ;
       graphdb:disable-sameAs "true" ;
       graphdb:query-timeout "0"
     ]
   ] .
"""


def build_graphdb_client() -> GraphDBClient:
    return GraphDBClient(
        base_url=GRAPHDB_BASE_URL,
        repository_id=GRAPHDB_REPOSITORY_ID,
    )


__all__ = [
    "GRAPHDB_BASE_URL",
    "GRAPHDB_REPOSITORY_ID",
    "GRAPHDB_REPOSITORY_URL",
    "GRAPHDB_SPARQL_ENDPOINT",
    "GRAPHDB_STATEMENTS_ENDPOINT",
    "GraphDBClient",
    "GraphDBClientError",
    "build_graphdb_client",
]
