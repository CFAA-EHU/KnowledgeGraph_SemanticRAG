from __future__ import annotations

import sys
import unittest
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
EXTRACTION_DIR = REPO_ROOT / "src" / "6_extraction"
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

from abox_extractor import (
    ABOX_PROMPT_VERSION,
    construir_prompt_sistema,
    detect_intra_chunk_identifier_duplicates,
    merge_intra_chunk_duplicates,
)

EX = Namespace("https://vocab.cfaa.eus/broaching/")


class AboxExtractorIdentityGuardrailTests(unittest.TestCase):
    def test_prompt_version_and_identity_rules_are_present(self) -> None:
        prompt = construir_prompt_sistema("- Clases permitidas: Parametro")

        self.assertIn("identity-rules", ABOX_PROMPT_VERSION)
        self.assertIn("REGLAS DE IDENTIDAD POR CLASE", prompt)
        self.assertIn("Para ex:Parametro", prompt)

    def test_intra_chunk_identifier_duplicates_are_detected_and_merged(self) -> None:
        graph = Graph()
        graph.add((EX.ParametroA, RDF.type, EX.Parametro))
        graph.add((EX.ParametroA, EX.identificador, Literal("PP177")))
        graph.add((EX.ParametroA, EX.textoExtracto, Literal("PP177 aparece.")))
        graph.add((EX.ParametroB, RDF.type, EX.Parametro))
        graph.add((EX.ParametroB, EX.identificador, Literal("PP-177")))
        graph.add((EX.ParametroB, EX.textoExtracto, Literal("PP-177 aparece repetido.")))
        graph.add((EX.ParametroB, EX.documentadoEn, EX.ManualX))

        conflicts = detect_intra_chunk_identifier_duplicates(graph)
        merged, resolved = merge_intra_chunk_duplicates(graph, conflicts)

        self.assertEqual(len(conflicts), 1)
        self.assertGreaterEqual(resolved, 1)
        subjects = {
            str(subject)
            for subject in merged.subjects(EX.identificador, None)
        }
        self.assertEqual(len(subjects), 1)


if __name__ == "__main__":
    unittest.main()
