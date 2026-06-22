"""Materialize missing owl:inverseOf triples in abox_linked.ttl and republish to GraphDB."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import json
import requests
from rdflib import Graph, URIRef
from rdflib.namespace import OWL

TBOX_PATH   = REPO_ROOT / "data/processed/ontology_aligned.ttl"
ABOX_PATH   = REPO_ROOT / "data/processed/abox_linked.ttl"
GRAPHDB_URL = "http://localhost:7200"
REPO_ID     = "semanticrag_operational_mirror"


def get_inverse_pairs(tbox: Graph) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []
    for s, _, o in tbox.triples((None, OWL.inverseOf, None)):
        key: tuple[str, str] = tuple(sorted([str(s), str(o)]))  # type: ignore[assignment]
        if key not in seen:
            seen.add(key)
            pairs.append((str(s), str(o)))
    return pairs


def materialize(abox: Graph, pairs: list[tuple[str, str]]) -> dict[str, int]:
    stats: dict[str, int] = {}
    for fwd, inv in pairs:
        added = 0
        fwd_uri = URIRef(fwd)
        inv_uri = URIRef(inv)
        # fwd → inv
        to_add = [
            (URIRef(o), inv_uri, URIRef(s))
            for s, p, o in abox.triples((None, fwd_uri, None))
            if isinstance(s, URIRef) and isinstance(o, URIRef)
            and not list(abox.triples((URIRef(o), inv_uri, URIRef(s))))
        ]
        for triple in to_add:
            abox.add(triple)
            added += 1
        # inv → fwd (symmetric closure)
        to_add2 = [
            (URIRef(o), fwd_uri, URIRef(s))
            for s, p, o in abox.triples((None, inv_uri, None))
            if isinstance(s, URIRef) and isinstance(o, URIRef)
            and not list(abox.triples((URIRef(o), fwd_uri, URIRef(s))))
        ]
        for triple in to_add2:
            abox.add(triple)
            added += 1
        if added:
            label = fwd.split("/")[-1] + " ↔ " + inv.split("/")[-1]
            stats[label] = added
    return stats


def republish(tbox_path: Path, abox_path: Path) -> int:
    base = f"{GRAPHDB_URL}/repositories/{REPO_ID}"
    # Clear and re-upload
    r = requests.delete(f"{base}/statements")
    r.raise_for_status()
    for path, content_type in [(tbox_path, "text/turtle"), (abox_path, "text/turtle")]:
        with open(path, "rb") as fh:
            r = requests.post(
                f"{base}/statements",
                headers={"Content-Type": content_type},
                data=fh,
            )
            r.raise_for_status()
    # Count triples
    r = requests.get(
        f"{GRAPHDB_URL}/repositories/{REPO_ID}",
        params={"query": "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"},
        headers={"Accept": "application/sparql-results+json"},
    )
    r.raise_for_status()
    return int(r.json()["results"]["bindings"][0]["n"]["value"])


def main() -> None:
    print("Loading T-Box ...")
    tbox = Graph()
    tbox.parse(TBOX_PATH, format="turtle")

    print("Loading A-Box ...")
    abox = Graph()
    abox.parse(ABOX_PATH, format="turtle")
    before = len(abox)

    pairs = get_inverse_pairs(tbox)
    print(f"Unique owl:inverseOf pairs: {len(pairs)}")

    print("Materializing inverses ...")
    stats = materialize(abox, pairs)
    after = len(abox)

    print(f"\nTriples before : {before}")
    print(f"Triples after  : {after}")
    print(f"Added          : {after - before}")
    for label, n in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {label}: +{n}")

    print("\nSerializing abox_linked.ttl ...")
    abox.serialize(destination=str(ABOX_PATH), format="turtle")

    print("Republishing to GraphDB ...")
    try:
        triple_count = republish(TBOX_PATH, ABOX_PATH)
        print(f"GraphDB: {triple_count} total triples")
    except Exception as e:
        print(f"[WARN] GraphDB republish failed: {e}")
        print("       Run publish_to_graphdb.py manually.")

    print("\nDONE")


if __name__ == "__main__":
    main()
