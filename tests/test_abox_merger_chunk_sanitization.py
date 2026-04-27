from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
EXTRACTION_DIR = REPO_ROOT / "src" / "6_extraction"
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

from abox_graph_sanitizer import EX
from abox_merger import merge_from_directory, merge_from_graphs


TBOX_TTL = """
@prefix ex: <https://vocab.cfaa.eus/broaching/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .

ex:InterfazUsuario a owl:Class .
ex:Parametro a owl:Class .
ex:identificador a owl:DatatypeProperty .
ex:textoExtracto a owl:DatatypeProperty .
"""


class AboxMergerChunkSanitizationTests(unittest.TestCase):
    def test_merger_sanitizes_each_chunk_before_union(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "chunk_001_abox.ttl").write_text(
                """
                @prefix ex: <https://vocab.cfaa.eus/broaching/> .
                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
                ex:MarcaGRTOSPDL a ex:InterfazUsuario ;
                    rdfs:label "Marca GRTOSPDL" ;
                    ex:identificador "GRTOSPDL" ;
                    ex:textoExtracto "Marca GRTOSPDL al gestor." .
                """,
                encoding="utf-8",
            )
            (tmp / "chunk_002_abox.ttl").write_text(
                """
                @prefix ex: <https://vocab.cfaa.eus/broaching/> .
                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
                ex:MarcaGRTOSPDL a ex:Parametro ;
                    rdfs:label "Marca GRTOSPDL (M[1108])" ;
                    ex:identificador "M[1108]" ;
                    ex:textoExtracto "V.PLC.M[1108]=1 ; Marca GRTOSPDL al gestor." .
                """,
                encoding="utf-8",
            )

            tbox_graph = Graph()
            tbox_graph.parse(data=TBOX_TTL, format="turtle")
            merged, ok, err, result = merge_from_directory(tmp, tbox_graph=tbox_graph, mint_registry={})

            self.assertEqual(ok, 2)
            self.assertEqual(err, 0)
            self.assertGreaterEqual(result.minted_nodes, 2)

            interfaz_nodes = list(merged.subjects(RDF.type, EX.InterfazUsuario))
            parametro_nodes = list(merged.subjects(RDF.type, EX.Parametro))
            self.assertEqual(len(interfaz_nodes), 1)
            self.assertEqual(len(parametro_nodes), 1)
            self.assertNotEqual(str(interfaz_nodes[0]), str(parametro_nodes[0]))
            self.assertNotEqual(str(interfaz_nodes[0]), str(EX.MarcaGRTOSPDL))
            self.assertNotEqual(str(parametro_nodes[0]), str(EX.MarcaGRTOSPDL))

    def test_global_merge_sanitizes_each_input_graph_before_union(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            graph_a = tmp / "manual_a_merged.ttl"
            graph_b = tmp / "manual_b_merged.ttl"
            graph_a.write_text(
                """
                @prefix ex: <https://vocab.cfaa.eus/broaching/> .
                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
                ex:MarcaGRTOSPDL a ex:InterfazUsuario ;
                    rdfs:label "Marca GRTOSPDL" ;
                    ex:identificador "GRTOSPDL" ;
                    ex:textoExtracto "Marca GRTOSPDL al gestor." .
                """,
                encoding="utf-8",
            )
            graph_b.write_text(
                """
                @prefix ex: <https://vocab.cfaa.eus/broaching/> .
                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
                ex:MarcaGRTOSPDL a ex:Parametro ;
                    rdfs:label "Marca GRTOSPDL (M[1108])" ;
                    ex:identificador "M[1108]" ;
                    ex:textoExtracto "V.PLC.M[1108]=1 ; Marca GRTOSPDL al gestor." .
                """,
                encoding="utf-8",
            )

            tbox_graph = Graph()
            tbox_graph.parse(data=TBOX_TTL, format="turtle")
            merged, ok, result = merge_from_graphs(
                [graph_a, graph_b],
                tbox_graph=tbox_graph,
                mint_registry={},
            )

            self.assertEqual(ok, 2)
            self.assertGreaterEqual(result.minted_nodes, 2)

            interfaz_nodes = list(merged.subjects(RDF.type, EX.InterfazUsuario))
            parametro_nodes = list(merged.subjects(RDF.type, EX.Parametro))
            self.assertEqual(len(interfaz_nodes), 1)
            self.assertEqual(len(parametro_nodes), 1)
            self.assertNotEqual(str(interfaz_nodes[0]), str(parametro_nodes[0]))
            self.assertNotEqual(str(interfaz_nodes[0]), str(EX.MarcaGRTOSPDL))
            self.assertNotEqual(str(parametro_nodes[0]), str(EX.MarcaGRTOSPDL))


if __name__ == "__main__":
    unittest.main()
