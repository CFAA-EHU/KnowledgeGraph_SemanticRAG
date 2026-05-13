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

from abox_canonicalizer import (
    apply_anchor_mapping,
    build_anchor_legacy_alias_mapping,
    build_anchor_mapping,
    load_canonical_anchors,
    protect_declared_canonical_anchors,
    rewrite_graph,
)

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

    def test_declared_anchor_mapping_rewrites_entities_but_not_type_objects(self) -> None:
        graph = Graph()
        graph.add((EX.SistemaDuplicado, RDF.type, EX.Sistema))
        graph.add((EX.RecursoY, EX.tieneComponente, EX.SistemaDuplicado))
        graph.add((EX.RecursoZ, RDF.type, EX.SistemaDuplicado))

        anchors = [
            {
                "canonical_uri": str(EX.SistemaCNC),
                "absorbs": [str(EX.SistemaDuplicado)],
                "class": "Sistema",
            }
        ]
        mapping = build_anchor_mapping(anchors)
        rewritten, stats = apply_anchor_mapping(graph, mapping)

        self.assertIn((EX.SistemaCNC, RDF.type, EX.Sistema), rewritten)
        self.assertIn((EX.RecursoY, EX.tieneComponente, EX.SistemaCNC), rewritten)
        self.assertIn((EX.RecursoZ, RDF.type, EX.SistemaDuplicado), rewritten)
        self.assertNotIn((EX.RecursoZ, RDF.type, EX.SistemaCNC), rewritten)
        self.assertEqual(stats["anchor_absorbed_count"], 1)

    def test_anchor_loader_rejects_cycles(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "canonical_anchors.json"
            path.write_text(
                """
                {
                  "anchors": [
                    {
                      "canonical_uri": "https://vocab.cfaa.eus/broaching/A",
                      "absorbs": ["https://vocab.cfaa.eus/broaching/B"]
                    },
                    {
                      "canonical_uri": "https://vocab.cfaa.eus/broaching/B",
                      "absorbs": ["https://vocab.cfaa.eus/broaching/C"]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_canonical_anchors(path)

    def test_declared_canonical_anchor_cannot_be_absorbed_later(self) -> None:
        candidates = [
            SimpleNamespace(source_uri=str(EX.AnchorCanonical), candidate_uri=str(EX.Other)),
            SimpleNamespace(source_uri=str(EX.Other), candidate_uri=str(EX.AnchorCanonical)),
        ]

        filtered, discarded = protect_declared_canonical_anchors(candidates, {str(EX.AnchorCanonical)})

        self.assertEqual(discarded, 1)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].source_uri, str(EX.Other))

    def test_legacy_aliases_are_mapped_without_graph_rewrite(self) -> None:
        anchors = [
            {
                "canonical_uri": str(EX.DirectivaSeguridadUE18),
                "absorbs": [],
                "legacy_aliases": [str(EX.DirectivaSeguridadUnionEuropea_18)],
            }
        ]

        mapping = build_anchor_legacy_alias_mapping(anchors)

        self.assertEqual(mapping[str(EX.DirectivaSeguridadUnionEuropea_18)], str(EX.DirectivaSeguridadUE18))


if __name__ == "__main__":
    unittest.main()
