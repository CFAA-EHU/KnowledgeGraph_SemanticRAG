from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CURRENT_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from artifact_contracts import (
    GRAPHDB_BASE_URL,
    GRAPHDB_PUBLICATION_REPORT_PATH,
    GRAPHDB_REPOSITORY_ID,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
)
from graphdb_client import GraphDBClientError, build_graphdb_client


COUNT_QUERY = "SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def publish_operational_graph() -> dict:
    client = build_graphdb_client()
    report = {
        "timestamp": _utc_now(),
        "graphdb_base_url": GRAPHDB_BASE_URL,
        "repository_id": GRAPHDB_REPOSITORY_ID,
        "tbox_path": str(OPERATIONAL_TBOX_PATH),
        "abox_path": str(OPERATIONAL_ABOX_PATH),
        "publication_status": "error",
        "repository_created": False,
        "uploaded_files": [],
        "triple_count": None,
        "errors": [],
    }

    try:
        client.healthcheck()
        repository_exists = client.repository_exists()
        if not repository_exists:
            client.create_repository()
            report["repository_created"] = True
        client.clear_repository()
        report["uploaded_files"].append(client.upload_turtle_file(OPERATIONAL_TBOX_PATH))
        report["uploaded_files"].append(client.upload_turtle_file(OPERATIONAL_ABOX_PATH))
        count_rows = client.run_select(COUNT_QUERY)
        if count_rows:
            report["triple_count"] = next(iter(count_rows[0].values()), None)
        report["publication_status"] = "ok"
    except GraphDBClientError as exc:
        report["errors"].append(str(exc))
    except Exception as exc:  # pragma: no cover - defensive runtime reporting
        report["errors"].append(f"unexpected_error: {exc}")

    GRAPHDB_PUBLICATION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAPHDB_PUBLICATION_REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    report = publish_operational_graph()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["publication_status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
