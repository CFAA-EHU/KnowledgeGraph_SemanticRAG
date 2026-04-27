from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from rdflib import Graph, Literal
from rdflib.namespace import RDF, RDFS

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
EXTRACTION_DIR = REPO_ROOT / "src" / "6_extraction"
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

from abox_graph_sanitizer import EX
from abox_graph_enricher import apply_enrichments
from abox_link_completer import apply_links
from abox_semantic_validator import SemanticVocabulary


class AboxEnrichmentGuardTests(unittest.TestCase):
    def test_enricher_only_accepts_label_or_datatype_surface_predicates(self) -> None:
        base = Graph()
        base.add((EX.SistemaX, RDF.type, EX.Sistema))

        surfaces = [
            SimpleNamespace(entity_uri=str(EX.SistemaX), added_property_uri=str(RDFS.label), added_value="Sistema X"),
            SimpleNamespace(entity_uri=str(EX.SistemaX), added_property_uri=str(EX.tieneComponente), added_value="No debe entrar"),
            SimpleNamespace(entity_uri=str(EX.SistemaX), added_property_uri=str(EX.textoExtracto), added_value="x" * 401),
        ]

        enriched, stats = apply_enrichments(
            base,
            links=[],
            surfaces=surfaces,
            allowed_surface_predicates={str(RDFS.label), str(EX.textoExtracto)},
        )

        self.assertIn((EX.SistemaX, RDFS.label, Literal("Sistema X")), enriched)
        self.assertEqual(stats["added_surface_count"], 1)
        self.assertEqual(stats["skipped_noncanonical_surface_predicate"], 1)
        self.assertEqual(stats["skipped_long_surface_value"], 1)

    def test_link_completer_rejects_invalid_link_shapes(self) -> None:
        base = Graph()
        base.add((EX.SistemaX, RDF.type, EX.Sistema))
        base.add((EX.ComponenteY, RDF.type, EX.Componente))
        vocabulary = SemanticVocabulary(
            classes={str(EX.Sistema), str(EX.Componente)},
            object_properties={str(EX.tieneComponente)},
            datatype_properties={str(EX.textoExtracto)},
        )
        links = [
            SimpleNamespace(source_uri=str(EX.SistemaX), predicate=str(EX.tieneComponente), target_uri=str(EX.ComponenteY), link_family="ok"),
            SimpleNamespace(source_uri=str(EX.SistemaX), predicate=str(EX.tieneComponente), target_uri=str(EX.SistemaX), link_family="self"),
            SimpleNamespace(source_uri=str(EX.Sistema), predicate=str(EX.tieneComponente), target_uri=str(EX.ComponenteY), link_family="class"),
            SimpleNamespace(source_uri=str(EX.SistemaX), predicate=str(EX.textoExtracto), target_uri=str(EX.ComponenteY), link_family="bad_pred"),
            SimpleNamespace(source_uri=str(EX.SistemaX), predicate=str(EX.tieneComponente), target_uri=str(EX.NoTipado), link_family="untyped"),
        ]

        linked, stats, _already_present = apply_links(base, links, vocabulary=vocabulary)

        self.assertIn((EX.SistemaX, EX.tieneComponente, EX.ComponenteY), linked)
        self.assertEqual(stats["added_link_count"], 1)
        self.assertEqual(stats["skipped_self_loop"], 1)
        self.assertEqual(stats["skipped_untyped"], 1)
        self.assertEqual(stats["skipped_noncanonical_predicate"], 1)
        self.assertEqual(stats["skipped_class_as_individual"], 1)


if __name__ == "__main__":
    unittest.main()
