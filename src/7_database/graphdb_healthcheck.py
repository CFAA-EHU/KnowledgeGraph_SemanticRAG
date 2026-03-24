from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CURRENT_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from artifact_contracts import GRAPHDB_BASE_URL, GRAPHDB_REPOSITORY_ID
from graphdb_client import GraphDBClientError, build_graphdb_client


COUNT_QUERY = "SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }"
ASK_QUERY = "ASK { ?s ?p ?o }"


def run_healthcheck() -> dict:
    client = build_graphdb_client()
    report = {
        "graphdb_base_url": GRAPHDB_BASE_URL,
        "repository_id": GRAPHDB_REPOSITORY_ID,
        "status": "server_unavailable",
        "server_available": False,
        "repository_exists": False,
        "repository_has_data": False,
        "triple_count": 0,
        "errors": [],
    }

    try:
        client.healthcheck()
        report["server_available"] = True
    except GraphDBClientError as exc:
        report["errors"].append(str(exc))
        return report

    try:
        exists = client.repository_exists()
        report["repository_exists"] = exists
        if not exists:
            report["status"] = "repository_missing"
            return report

        ask_result = client.run_ask(ASK_QUERY)
        count_rows = client.run_select(COUNT_QUERY)
        triple_count = 0
        if count_rows:
            raw_count = next(iter(count_rows[0].values()), "0")
            try:
                triple_count = int(raw_count)
            except ValueError:
                triple_count = 0
        report["repository_has_data"] = ask_result or triple_count > 0
        report["triple_count"] = triple_count
        report["status"] = "repository_ready" if report["repository_has_data"] else "repository_empty"
        return report
    except GraphDBClientError as exc:
        report["errors"].append(str(exc))
        report["status"] = "repository_missing"
        return report


def main() -> None:
    report = run_healthcheck()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "repository_ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
