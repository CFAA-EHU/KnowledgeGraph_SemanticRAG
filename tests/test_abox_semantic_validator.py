from __future__ import annotations

import sys
import unittest
from pathlib import Path

from rdflib import Graph

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
EXTRACTION_DIR = REPO_ROOT / "src" / "6_extraction"
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

from abox_semantic_validator import SemanticVocabulary, validate_abox_graph


VOCABULARY = SemanticVocabulary(
    classes={
        "https://vocab.cfaa.eus/broaching/Sistema",
        "https://vocab.cfaa.eus/broaching/Maquina",
    },
    object_properties={"https://vocab.cfaa.eus/broaching/tieneComponente"},
    datatype_properties={
        "https://vocab.cfaa.eus/broaching/identificador",
        "https://vocab.cfaa.eus/broaching/textoExtracto",
    },
)


def load_graph(ttl_text: str) -> Graph:
    graph = Graph()
    graph.parse(data=ttl_text, format="turtle")
    return graph


class AboxSemanticValidatorTests(unittest.TestCase):
    def test_detects_individual_used_as_class(self) -> None:
        graph = load_graph(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:MaquinaBrochadoExterior_18 a ex:Maquina ;
                rdfs:label "Maquina brochadora" ;
                ex:textoExtracto "Maquina descrita." .
            ex:SistemaX a ex:MaquinaBrochadoExterior_18 ;
                ex:textoExtracto "Sistema descrito." .
            """
        )

        result = validate_abox_graph(graph, vocabulary=VOCABULARY)
        self.assertIn("individual_used_as_class", result.error_categories)
        self.assertFalse(result.ok)

    def test_reports_long_local_name_as_diagnostic(self) -> None:
        long_local = "Sistema" + ("CambioHerramienta" * 8)
        graph = load_graph(
            f"""
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            ex:{long_local} a ex:Sistema ;
                ex:textoExtracto "Sistema descrito." .
            """
        )

        result = validate_abox_graph(graph, vocabulary=VOCABULARY)
        self.assertIn("long_local_name", result.error_categories)
        self.assertGreater(result.long_local_name_entities, 0)


if __name__ == "__main__":
    unittest.main()
