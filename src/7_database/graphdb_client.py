from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests


class GraphDBClientError(RuntimeError):
    pass


class GraphDBClient:
    def __init__(self, base_url: str, repository_id: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.repository_id = repository_id
        self.timeout = timeout
        self.session = requests.Session()

    @property
    def repositories_api_url(self) -> str:
        return f"{self.base_url}/rest/repositories"

    @property
    def repository_api_url(self) -> str:
        return f"{self.repositories_api_url}/{self.repository_id}"

    @property
    def repository_query_url(self) -> str:
        return f"{self.base_url}/repositories/{self.repository_id}"

    @property
    def repository_statements_url(self) -> str:
        return f"{self.repository_query_url}/statements"

    @property
    def repository_size_url(self) -> str:
        return f"{self.repository_api_url}/size"

    def _raise_for_status(self, response: requests.Response, context: str) -> None:
        if response.ok:
            return
        body = response.text.strip()
        raise GraphDBClientError(
            f"{context}: HTTP {response.status_code} - {body or 'empty response body'}"
        )

    def healthcheck(self) -> dict[str, Any]:
        try:
            response = self.session.get(
                self.repositories_api_url,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
            self._raise_for_status(response, "Could not reach GraphDB")
            payload = response.json()
            return {
                "ok": True,
                "base_url": self.base_url,
                "repository_id": self.repository_id,
                "repositories_visible": len(payload) if isinstance(payload, list) else None,
            }
        except Exception as exc:
            return {
                "ok": False,
                "base_url": self.base_url,
                "repository_id": self.repository_id,
                "error": str(exc),
            }

    def repository_exists(self) -> bool:
        response = self.session.get(
            self.repositories_api_url,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        self._raise_for_status(response, "Could not list GraphDB repositories")
        payload = response.json()
        if not isinstance(payload, list):
            return False
        return any(repo.get("id") == self.repository_id for repo in payload if isinstance(repo, dict))

    def create_repository(self, config_ttl: str) -> None:
        files = {
            "config": ("repo-config.ttl", config_ttl.encode("utf-8"), "text/turtle"),
        }
        response = self.session.post(
            self.repositories_api_url,
            files=files,
            timeout=self.timeout,
        )
        self._raise_for_status(
            response,
            f"Could not create GraphDB repository {self.repository_id}",
        )

    def delete_repository(self) -> bool:
        response = self.session.delete(
            self.repository_api_url,
            timeout=self.timeout,
        )
        if response.status_code == 404:
            return False
        self._raise_for_status(
            response,
            f"Could not delete GraphDB repository {self.repository_id}",
        )
        return True

    def upload_turtle_file(self, file_path: str | Path, context: str | None = None) -> None:
        path = Path(file_path)
        if not path.exists():
            raise GraphDBClientError(f"Turtle file does not exist: {path}")

        params: dict[str, str] = {}
        if context:
            params["context"] = f"<{context}>"

        response = self.session.post(
            self.repository_statements_url,
            params=params,
            data=path.read_bytes(),
            headers={"Content-Type": "text/turtle"},
            timeout=max(self.timeout, 120),
        )
        self._raise_for_status(
            response,
            f"Could not upload Turtle file {path.name} to {self.repository_id}",
        )

    def run_select_raw(self, query: str) -> dict[str, Any]:
        response = self.session.post(
            self.repository_query_url,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=max(self.timeout, 120),
        )
        self._raise_for_status(response, "Could not execute SELECT query")
        return response.json()

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

    def run_ask(self, query: str) -> bool:
        response = self.session.post(
            self.repository_query_url,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=max(self.timeout, 120),
        )
        self._raise_for_status(response, "Could not execute ASK query")
        payload = response.json()
        return bool(payload.get("boolean"))

    def run_update(self, update: str) -> None:
        response = self.session.post(
            self.repository_statements_url,
            data={"update": update},
            timeout=max(self.timeout, 120),
        )
        self._raise_for_status(response, "Could not execute SPARQL update")

    def get_repository_size(self) -> int | None:
        response = self.session.get(
            self.repository_size_url,
            timeout=self.timeout,
        )
        self._raise_for_status(
            response,
            f"Could not get triple count for repository {self.repository_id}",
        )
        text = response.text.strip()
        try:
            return int(text)
        except ValueError:
            return None


def build_graphdb_client() -> GraphDBClient:
    from artifact_contracts import GRAPHDB_BASE_URL, GRAPHDB_REPOSITORY_ID

    return GraphDBClient(
        base_url=GRAPHDB_BASE_URL,
        repository_id=GRAPHDB_REPOSITORY_ID,
    )


if __name__ == "__main__":
    client = build_graphdb_client()
    print(json.dumps(client.healthcheck(), ensure_ascii=False, indent=2))
