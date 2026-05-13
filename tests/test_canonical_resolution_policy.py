from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
EXTRACTION_DIR = REPO_ROOT / "src" / "6_extraction"
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

import canonical_resolution_policy as policy
from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF

EX = Namespace("https://vocab.cfaa.eus/broaching/")


class CanonicalResolutionPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_closure = policy._TBOX_SUBCLASS_CLOSURE
        self.previous_disjoint_pairs = policy._TBOX_DISJOINT_PAIRS
        policy._TBOX_SUBCLASS_CLOSURE = {
            "ComponenteElectrico": {"Componente"},
        }
        policy._TBOX_DISJOINT_PAIRS = {frozenset({"Empresa", "Directiva"})}

    def tearDown(self) -> None:
        policy._TBOX_SUBCLASS_CLOSURE = self.previous_closure
        policy._TBOX_DISJOINT_PAIRS = self.previous_disjoint_pairs

    def test_types_are_compatible_by_subclass(self) -> None:
        self.assertTrue(policy._types_compatible(["ComponenteElectrico"], ["Componente"]))

    def test_types_without_hierarchy_are_not_merged(self) -> None:
        self.assertFalse(policy._types_compatible(["Parametro"], ["InterfazUsuario"]))

    def test_manual_conflict_pair_is_rejected(self) -> None:
        self.assertFalse(policy._types_compatible(["Maquina"], ["Manual"]))

    def test_tbox_disjoint_pair_is_rejected(self) -> None:
        self.assertFalse(policy._types_compatible(["Empresa"], ["Directiva"]))

    def test_collect_identifier_based_candidates_merges_priority_classes(self) -> None:
        graph = Graph()
        graph.add((EX.ParametroA, RDF.type, EX.Parametro))
        graph.add((EX.ParametroA, EX.identificador, Literal("PP177")))
        graph.add((EX.ParametroA, EX.textoExtracto, Literal("PP177 en tabla.")))
        graph.add((EX.ParametroB, RDF.type, EX.Parametro))
        graph.add((EX.ParametroB, EX.identificador, Literal("PP-177")))
        graph.add((EX.ParametroB, EX.textoExtracto, Literal("PP-177 repetido.")))
        graph.add((EX.ParametroA, EX.documentadoEn, EX.ManualX))

        candidates = policy.collect_identifier_based_candidates(graph)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].candidate_origin, "identifier_exact_match")
        self.assertEqual(candidates[0].evidence["identifier_norm"], "PP177")

    def test_identifier_candidates_ignore_non_priority_classes(self) -> None:
        graph = Graph()
        graph.add((EX.SistemaA, RDF.type, EX.Sistema))
        graph.add((EX.SistemaA, EX.identificador, Literal("SYS1")))
        graph.add((EX.SistemaB, RDF.type, EX.Sistema))
        graph.add((EX.SistemaB, EX.identificador, Literal("SYS1")))

        self.assertEqual(policy.collect_identifier_based_candidates(graph), [])


if __name__ == "__main__":
    unittest.main()
