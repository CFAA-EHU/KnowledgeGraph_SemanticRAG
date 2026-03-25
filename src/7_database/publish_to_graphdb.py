from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from artifact_contracts import (
    GRAPHDB_BASE_URL,
    GRAPHDB_PUBLICATION_REPORT_PATH,
    GRAPHDB_REPOSITORY_ID,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
)

from graphdb_client import GraphDBClient, GraphDBClientError

COUNT_QUERY = "SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }"


def build_repository_config_ttl(repository_id: str, title: str | None = None) -> str:
    repo_title = title or repository_id
    return f"""@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix rep: <http://www.openrdf.org/config/repository#> .
@prefix sr: <http://www.openrdf.org/config/repository/sail#> .
@prefix sail: <http://www.openrdf.org/config/sail#> .
@prefix graphdb: <http://www.ontotext.com/config/graphdb#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<#repo> a rep:Repository ;
    rep:repositoryID "{repository_id}" ;
    rdfs:label "{repo_title}" ;
    rep:repositoryImpl [
        rep:repositoryType "graphdb:SailRepository" ;
        sr:sailImpl [
            sail:sailType "graphdb:Sail" ;
            graphdb:base-URL "http://example.org/semanticrag#" ;
            graphdb:defaultNS "" ;
            graphdb:entity-id-size "32" ;
            graphdb:repository-type "file-repository" ;
            graphdb:ruleset "rdfsplus-optimized" ;
            graphdb:disable-sameAs "true" ;
            graphdb:enable-context-index "false" ;
            graphdb:enablePredicateList "true" ;
            graphdb:enable-literal-index "true" ;
            graphdb:enable-fts-index "false" ;
            graphdb:fts-string-literals-index "default" ;
            graphdb:fts-iris-index "none" ;
            graphdb:fts-indexes ("default" "iri") ;
            graphdb:imports "" ;
            graphdb:read-only "false" ;
            graphdb:check-for-inconsistencies "false" ;
            graphdb:query-timeout "0" ;
            graphdb:query-limit-results "0" ;
            graphdb:storage-folder "storage"
        ]
    ] .
"""


def write_report(report: dict) -> None:
    GRAPHDB_PUBLICATION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAPHDB_PUBLICATION_REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    client = GraphDBClient(
        base_url=GRAPHDB_BASE_URL,
        repository_id=GRAPHDB_REPOSITORY_ID,
    )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "graphdb_base_url": GRAPHDB_BASE_URL,
        "repository_id": GRAPHDB_REPOSITORY_ID,
        "tbox_path": str(OPERATIONAL_TBOX_PATH),
        "abox_path": str(OPERATIONAL_ABOX_PATH),
        "publication_status": "started",
        "repository_existed_before": None,
        "repository_deleted_before_recreate": False,
        "repository_created": False,
        "uploaded_files": [],
        "triple_count": None,
        "errors": [],
    }

    try:
        health = client.healthcheck()
        if not health.get("ok"):
            raise GraphDBClientError(
                f"GraphDB server_unavailable: {health.get('error', 'unknown error')}"
            )

        if not Path(OPERATIONAL_TBOX_PATH).exists():
            raise FileNotFoundError(f"Missing operational T-Box: {OPERATIONAL_TBOX_PATH}")
        if not Path(OPERATIONAL_ABOX_PATH).exists():
            raise FileNotFoundError(f"Missing operational A-Box: {OPERATIONAL_ABOX_PATH}")

        repo_exists = client.repository_exists()
        report["repository_existed_before"] = repo_exists

        # CAMBIO CLAVE:
        # - si el repo no existe: crear y NO limpiar
        # - si el repo existe: borrar y recrear
        if repo_exists:
            deleted = client.delete_repository()
            report["repository_deleted_before_recreate"] = deleted

        config_ttl = build_repository_config_ttl(
            repository_id=GRAPHDB_REPOSITORY_ID,
            title=f"{GRAPHDB_REPOSITORY_ID} operational mirror",
        )
        client.create_repository(config_ttl)
        report["repository_created"] = True

        client.upload_turtle_file(OPERATIONAL_TBOX_PATH)
        report["uploaded_files"].append(
            {"path": str(OPERATIONAL_TBOX_PATH), "status": "uploaded"}
        )

        client.upload_turtle_file(OPERATIONAL_ABOX_PATH)
        report["uploaded_files"].append(
            {"path": str(OPERATIONAL_ABOX_PATH), "status": "uploaded"}
        )

        report["triple_count"] = client.get_repository_size()
        if report["triple_count"] is None:
            count_rows = client.run_select(COUNT_QUERY)
            if count_rows:
                raw_count = next(iter(count_rows[0].values()), None)
                try:
                    report["triple_count"] = int(raw_count) if raw_count is not None else None
                except (TypeError, ValueError):
                    report["triple_count"] = raw_count
        report["publication_status"] = "ok"

    except Exception as exc:
        report["publication_status"] = "error"
        report["errors"].append(str(exc))

    write_report(report)


if __name__ == "__main__":
    main()
