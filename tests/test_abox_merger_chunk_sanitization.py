from __future__ import annotations

import sys
import tempfile
import unittest
import json
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
EXTRACTION_DIR = REPO_ROOT / "src" / "6_extraction"
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

from abox_graph_sanitizer import EX
from abox_merger import (
    merge_from_directory,
    merge_from_graphs,
    report_identifier_collisions,
    sanitize_final_merged_graph,
    write_marked_chunks_report,
)
from abox_semantic_validator import SemanticVocabulary


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

VOCABULARY = SemanticVocabulary(
    classes={
        str(EX.InterfazUsuario),
        str(EX.Parametro),
    },
    object_properties=set(),
    datatype_properties={
        str(EX.identificador),
        str(EX.textoExtracto),
    },
)


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

    def test_merger_rejects_chunk_with_individual_used_as_class(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "chunk_001_abox.ttl").write_text(
                """
                @prefix ex: <https://vocab.cfaa.eus/broaching/> .
                @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
                ex:MarcaGRTOSPDL a ex:Parametro ;
                    rdfs:label "Marca GRTOSPDL" ;
                    ex:textoExtracto "Marca GRTOSPDL." .
                ex:OtroNodo a ex:MarcaGRTOSPDL ;
                    ex:textoExtracto "Uso incorrecto como clase." .
                """,
                encoding="utf-8",
            )

            tbox_graph = Graph()
            tbox_graph.parse(data=TBOX_TTL, format="turtle")
            rejected: list[dict[str, object]] = []
            warned: list[dict[str, object]] = []
            merged, ok, err, _result = merge_from_directory(
                tmp,
                tbox_graph=tbox_graph,
                mint_registry={},
                vocabulary=VOCABULARY,
                rejected_inputs=rejected,
                warned_inputs=warned,
            )

            self.assertEqual(ok, 0)
            self.assertEqual(err, 1)
            self.assertEqual(len(merged), 0)
            self.assertEqual(rejected[0]["failures"]["individual_used_as_class"], 1)

    def test_final_merge_sanitization_does_not_mint_new_iris(self) -> None:
        graph = Graph()
        graph.add((EX.ParametroX, RDF.type, EX.Parametro))
        graph.add((EX.ParametroX, EX.textoExtracto, URIRef("https://vocab.cfaa.eus/broaching/TextoComoObjeto")))
        tbox_graph = Graph()
        tbox_graph.parse(data=TBOX_TTL, format="turtle")

        sanitized, result = sanitize_final_merged_graph(graph, tbox_graph=tbox_graph)

        self.assertEqual(result.minted_nodes, 0)
        self.assertEqual(result.hash_due_to_weak_identity, 0)
        self.assertIn((EX.ParametroX, RDF.type, EX.Parametro), sanitized)

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

    def test_identifier_collision_report_groups_same_type_and_identifier(self) -> None:
        graph = Graph()
        graph.add((EX.ParametroA, RDF.type, EX.Parametro))
        graph.add((EX.ParametroA, EX.identificador, URIRef("https://example.org/not-a-literal")))
        graph.add((EX.ParametroA, EX.identificador, Literal("PP177")))
        graph.add((EX.ParametroB, RDF.type, EX.Parametro))
        graph.add((EX.ParametroB, EX.identificador, Literal("PP-177")))

        report = report_identifier_collisions(graph)

        self.assertEqual(report["total_collision_groups"], 1)
        self.assertEqual(report["collisions_by_class"]["Parametro"], 1)

    def test_marked_chunks_report_is_written_for_nonblocking_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "abox_merger_marked_chunks.json"
            warnings = [{"path": "chunk_001_abox.ttl", "warnings": {"long_local_name": 1}}]

            write_marked_chunks_report(output, warnings)

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["marked_count"], 1)
            self.assertEqual(payload["chunks"][0]["warnings"]["long_local_name"], 1)


if __name__ == "__main__":
    unittest.main()
