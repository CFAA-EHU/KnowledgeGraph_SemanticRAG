from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
EXTRACTION_DIR = REPO_ROOT / "src" / "6_extraction"
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

from abox_canonicalizer import rewrite_graph

EX = Namespace("https://vocab.cfaa.eus/broaching/")


def selection(source: URIRef, canonical: URIRef, supplemental_targets: list[URIRef] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        source_uri=str(source),
        canonical_uri=str(canonical),
        entity_type="test",
        resolution_reason="test",
        rules_applied=["test"],
        support_question_ids=[],
        supplemental_targets=[str(uri) for uri in supplemental_targets or []],
        selection_scores={},
    )


class AboxCanonicalizerTests(unittest.TestCase):
    def test_rewrite_graph_does_not_rewrite_rdf_type_objects(self) -> None:
        graph = Graph()
        graph.add((EX.SistemaCNC, RDF.type, EX.Sistema))
        graph.add((EX.Sistema, RDFS.label, Literal("Sistema")))

        rewritten, stats, _ = rewrite_graph(
            graph,
            [selection(EX.Sistema, EX.SistemaCanonicalizado)],
        )

        self.assertIn((EX.SistemaCNC, RDF.type, EX.Sistema), rewritten)
        self.assertNotIn((EX.SistemaCNC, RDF.type, EX.SistemaCanonicalizado), rewritten)
        self.assertEqual(stats["rewritten_objects"], 0)

    def test_supplemental_links_skip_rdf_type_incoming_links(self) -> None:
        graph = Graph()
        graph.add((EX.RecursoX, RDF.type, EX.Sistema))
        graph.add((EX.RecursoY, EX.tieneComponente, EX.Sistema))

        rewritten, stats, _ = rewrite_graph(
            graph,
            [selection(EX.Sistema, EX.Sistema, supplemental_targets=[EX.SistemaSuplementario])],
        )

        self.assertNotIn((EX.RecursoX, RDF.type, EX.SistemaSuplementario), rewritten)
        self.assertIn((EX.RecursoY, EX.tieneComponente, EX.SistemaSuplementario), rewritten)
        self.assertEqual(stats["supplemental_links_added"], 1)


if __name__ == "__main__":
    unittest.main()
