from __future__ import annotations

import json
import unittest
import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.compare import to_isomorphic
from rdflib.namespace import RDF, RDFS, XSD

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
EXTRACTION_DIR = REPO_ROOT / "src" / "6_extraction"
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

from abox_graph_sanitizer import EX, sanitize_abox_graph
from abox_extractor import (
    construir_ttl_chunk_no_informativo,
    es_chunk_no_informativo,
    parse_ttl_graph,
    sanitize_generated_ttl,
)
from abox_semantic_validator import load_semantic_vocabulary, validate_ttl_text_semantics


TBOX_TTL = """
@prefix ex: <https://vocab.cfaa.eus/broaching/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .

ex:Sistema a owl:Class .
ex:Componente a owl:Class .
ex:ComponenteElectrico a owl:Class ; rdfs:subClassOf ex:Componente .
ex:Sensor a owl:Class ; rdfs:subClassOf ex:Componente .
ex:Pagina a owl:Class .
ex:InterfazUsuario a owl:Class .
ex:Parametro a owl:Class .
ex:TareaMantenimiento a owl:Class .
ex:ModoOperacion a owl:Class .
ex:Tabla a owl:Class .

ex:tieneComponente a owl:ObjectProperty .
ex:identificador a owl:DatatypeProperty .
ex:textoExtracto a owl:DatatypeProperty .
ex:valor a owl:DatatypeProperty .
"""


def load_graph_from_text(ttl_text: str) -> Graph:
    graph = Graph()
    graph.parse(data=ttl_text, format="turtle")
    return graph


class AboxGraphSanitizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tbox_graph = load_graph_from_text(TBOX_TTL)
        self.registry: dict[str, str] = {}

    def test_blank_node_subject_is_minted(self) -> None:
        graph = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            [] a ex:Componente ;
               rdfs:label "Motor principal" ;
               ex:textoExtracto "Motor principal del conjunto." .
            """
        )

        sanitized, _ = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        subjects = list(sanitized.subjects(RDF.type, EX.Componente))
        self.assertEqual(len(subjects), 1)
        self.assertIsInstance(subjects[0], URIRef)
        self.assertTrue(str(subjects[0]).startswith(str(EX)))

    def test_blank_node_object_is_minted_and_rewritten(self) -> None:
        graph = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:SistemaCNC a ex:Sistema ;
                ex:tieneComponente [
                    a ex:Sensor ;
                    rdfs:label "Encoder principal" ;
                    ex:identificador "ENC-1" ;
                    ex:textoExtracto "Encoder principal del eje X."
                ] .
            """
        )

        sanitized, _ = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        targets = list(sanitized.objects(EX.SistemaCNC, EX.tieneComponente))
        self.assertEqual(len(targets), 1)
        self.assertIsInstance(targets[0], URIRef)
        self.assertEqual([str(obj) for obj in sanitized.objects(targets[0], EX.identificador)], ["ENC-1"])
        self.assertTrue(any(True for _ in sanitized.triples((targets[0], RDF.type, EX.Sensor))))

    def test_rdf_type_object_is_not_minted_or_rewritten(self) -> None:
        graph = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:Maquina a ex:Componente ;
                rdfs:label "Maquina como recurso descrito" ;
                ex:identificador "M-1" ;
                ex:textoExtracto "Recurso descrito para probar la proteccion de rdf:type." .
            ex:SistemaX a ex:Maquina .
            """
        )

        sanitized, report = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        self.assertIn((EX.SistemaX, RDF.type, EX.Maquina), sanitized)
        self.assertGreaterEqual(report.type_object_minting_prevented, 1)

    def test_texto_extracto_is_not_used_as_primary_uri_surface(self) -> None:
        long_extract = (
            "Es el almacen tipico de torno para efectuar el cambio el almacen gira "
            "hasta posicionar la herramienta solicitada y despues se ejecuta la secuencia."
        )
        graph = load_graph_from_text(
            f"""
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            [] a ex:Sistema ;
                ex:textoExtracto {json.dumps(long_extract)} .
            """
        )

        sanitized, report = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        subject = next(sanitized.subjects(RDF.type, EX.Sistema))
        local_name = str(subject).rsplit("/", 1)[-1]
        self.assertRegex(local_name, r"^Sistema_[0-9a-f]{10}$")
        self.assertLessEqual(len(local_name), 80)
        self.assertEqual(report.hash_due_to_weak_identity, 1)

    def test_long_new_local_name_is_truncated_with_hash(self) -> None:
        long_label = "Sistema " + ("Cambio Herramienta " * 10)
        graph = load_graph_from_text(
            f"""
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            [] a ex:Sistema ;
                rdfs:label {json.dumps(long_label)} ;
                ex:textoExtracto "Sistema de cambio de herramienta." .
            """
        )

        sanitized, report = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        subject = next(sanitized.subjects(RDF.type, EX.Sistema))
        local_name = str(subject).rsplit("/", 1)[-1]
        self.assertLessEqual(len(local_name), 80)
        self.assertRegex(local_name, r"_[0-9a-f]{10}$")
        self.assertEqual(report.long_local_name_truncated, 1)

    def test_file_iris_are_replaced_or_purged(self) -> None:
        graph = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            <file:///tmp/domain-node> a ex:Componente ;
                rdfs:label "Sensor de posicion" ;
                ex:textoExtracto "Sensor de posicion del sistema." .
            <file:///tmp/artifact> ex:tieneComponente ex:SistemaCNC .
            ex:SistemaCNC a ex:Sistema .
            """
        )

        sanitized, _ = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        serialized = sanitized.serialize(format="turtle")
        self.assertNotIn("file:///", serialized)
        self.assertTrue(any(True for subject in sanitized.subjects(RDF.type, EX.Componente) if isinstance(subject, URIRef)))

    def test_redundant_types_are_removed(self) -> None:
        graph = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            ex:ModuloX a ex:ComponenteElectrico, ex:Componente .
            """
        )

        sanitized, _ = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        types = {obj for obj in sanitized.objects(EX.ModuloX, RDF.type)}
        self.assertEqual(types, {EX.ComponenteElectrico})

    def test_incidental_table_type_is_removed_from_function_entity(self) -> None:
        graph = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:Funcion_DMC a ex:ModoOperacion, ex:Tabla ;
                rdfs:label "Función #DMC" ;
                ex:identificador "#DMC" ;
                ex:textoExtracto "En la función #DMC, el avance mínimo es mayor que el avance máximo." .
            """
        )

        sanitized, report = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        subject = next(sanitized.subjects(RDFS.label, Literal("Función #DMC")))
        types = {obj for obj in sanitized.objects(subject, RDF.type)}
        self.assertEqual(types, {EX.ModoOperacion})
        self.assertEqual(report.incidental_table_types_removed, 1)

    def test_real_table_type_is_preserved(self) -> None:
        graph = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:TablaFuncionesM a ex:Tabla ;
                rdfs:label "Tabla de funciones M" ;
                ex:textoExtracto "Tabla de funciones M para control de movimientos." .
            """
        )

        sanitized, report = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        self.assertIn((EX.TablaFuncionesM, RDF.type, EX.Tabla), sanitized)
        self.assertEqual(report.incidental_table_types_removed, 0)

    def test_missing_type_is_inferred_from_property_domain(self) -> None:
        graph = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:DepositoRefrigeracion200L rdfs:label "Deposito Refrigeracion 200 L" ;
                ex:requiereConsumible ex:AceiteCorte .
            ex:AceiteCorte a ex:Consumible ;
                rdfs:label "Aceite de corte" ;
                ex:textoExtracto "Aceite de corte." .
            """
        )

        self.tbox_graph.add((EX.Consumible, RDF.type, URIRef("http://www.w3.org/2002/07/owl#Class")))
        self.tbox_graph.add((EX.requiereConsumible, RDFS.domain, EX.Sistema))
        sanitized, report = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        self.assertIn((EX.DepositoRefrigeracion200L, RDF.type, EX.Sistema), sanitized)
        self.assertEqual(report.inferred_missing_types, 1)

    def test_minimal_traceability_is_added_from_label(self) -> None:
        graph = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:OVERTEMP a ex:InterfazUsuario ;
                rdfs:label "OVERTEMP" ;
                ex:identificador "OVERTEMP" .
            """
        )

        sanitized, report = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        subject = next(sanitized.subjects(RDFS.label, Literal("OVERTEMP")))
        self.assertEqual([str(obj) for obj in sanitized.objects(subject, EX.textoExtracto)], ["OVERTEMP"])
        self.assertEqual(report.texto_extracto_added_from_traceability, 1)

    def test_texto_extracto_equal_to_chunk_is_removed(self) -> None:
        chunk_text = "Este es el texto completo del chunk y no describe de forma especifica la entidad."
        graph = load_graph_from_text(
            f"""
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:MotorPrincipal a ex:Componente ;
                rdfs:label "Motor principal" ;
                ex:textoExtracto "{chunk_text}" .
            """
        )

        sanitized, _ = sanitize_abox_graph(
            graph,
            tbox_graph=self.tbox_graph,
            source_chunk_text=chunk_text,
            mint_registry=self.registry,
        )
        self.assertEqual(list(sanitized.objects(EX.MotorPrincipal, EX.textoExtracto)), [])

    def test_texto_extracto_short_and_specific_is_preserved(self) -> None:
        graph = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:MotorPrincipal a ex:Componente ;
                rdfs:label "Motor principal" ;
                ex:textoExtracto "Motor principal del cabezal." .
            """
        )

        sanitized, _ = sanitize_abox_graph(
            graph,
            tbox_graph=self.tbox_graph,
            source_chunk_text="Texto de chunk mayor y distinto.",
            mint_registry=self.registry,
        )
        extracts = [str(obj) for obj in sanitized.objects(EX.MotorPrincipal, EX.textoExtracto)]
        self.assertEqual(extracts, ["Motor principal del cabezal."])

    def test_texto_extracto_chunk_like_is_scoped_when_possible(self) -> None:
        chunk_text = (
            "| Command. | Meaning. | Format. |\n"
            "| % | Program header. | 14 characters. |\n"
            "| [ ] | Text type block label. | 14 characters. |"
        )
        graph = load_graph_from_text(
            f"""
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:TablaComandos a ex:Pagina ;
                rdfs:label "Programming commands table"@en ;
                ex:textoExtracto {json.dumps(chunk_text)}@en .
            """
        )

        sanitized, _ = sanitize_abox_graph(
            graph,
            tbox_graph=self.tbox_graph,
            source_chunk_text=chunk_text,
            mint_registry=self.registry,
        )
        extracts = [str(obj) for obj in sanitized.objects(EX.TablaComandos, EX.textoExtracto)]
        self.assertEqual(len(extracts), 1)
        self.assertNotEqual(extracts[0], chunk_text)
        self.assertIn("Command.", extracts[0])

    def test_sanitizer_is_idempotent(self) -> None:
        graph = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:SistemaCNC a ex:Sistema ;
                ex:tieneComponente [
                    a ex:Sensor ;
                    rdfs:label "Encoder principal" ;
                    ex:identificador "ENC-1" ;
                    ex:textoExtracto "Encoder principal del eje X."
                ] .
            """
        )

        once, _ = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        twice, _ = sanitize_abox_graph(once, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        self.assertEqual(to_isomorphic(once), to_isomorphic(twice))

    def test_registry_reuses_same_iri_for_same_entity_key(self) -> None:
        graph_one = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            [] a ex:Sensor ;
               rdfs:label "Encoder principal" ;
               ex:identificador "ENC-1" ;
               ex:textoExtracto "Encoder principal del eje X." .
            """
        )
        graph_two = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            [] a ex:Sensor ;
               rdfs:label "Encoder principal" ;
               ex:identificador "ENC-1" ;
               ex:textoExtracto "Encoder principal del eje X." .
            """
        )

        sanitized_one, _ = sanitize_abox_graph(graph_one, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        sanitized_two, _ = sanitize_abox_graph(graph_two, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        uri_one = next(sanitized_one.subjects(RDF.type, EX.Sensor))
        uri_two = next(sanitized_two.subjects(RDF.type, EX.Sensor))
        self.assertEqual(str(uri_one), str(uri_two))

    def test_registry_avoids_reusing_same_uri_for_distinct_keys(self) -> None:
        graph_one = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            [] a ex:InterfazUsuario ;
               rdfs:label "Marca CH1TOSPDL" ;
               ex:identificador "CH1TOSPDL" ;
               ex:textoExtracto "Marca CH1TOSPDL en pantalla." .
            """
        )
        graph_two = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            [] a ex:Parametro ;
               rdfs:label "Marca CH1TOSPDL" ;
               ex:identificador "M[1102]" ;
               ex:textoExtracto "Marca CH1TOSPDL asociada al parametro M[1102]." .
            """
        )

        sanitized_one, _ = sanitize_abox_graph(graph_one, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        sanitized_two, _ = sanitize_abox_graph(graph_two, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        uri_one = next(sanitized_one.subjects(RDF.type, EX.InterfazUsuario))
        uri_two = next(sanitized_two.subjects(RDF.type, EX.Parametro))
        self.assertNotEqual(str(uri_one), str(uri_two))

    def test_invalid_hex_binary_literals_are_downgraded(self) -> None:
        graph = Graph()
        graph.add((EX.ParametroX, RDF.type, EX.Componente))
        graph.add((EX.ParametroX, EX.textoExtracto, Literal("Parametro de prueba.")))
        graph.add((EX.ParametroX, EX.valor, Literal("8", datatype=XSD.hexBinary)))

        sanitized, report = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        subject = next(sanitized.subjects(RDF.type, EX.Componente))
        values = list(sanitized.objects(subject, EX.valor))
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].datatype, XSD.string)
        self.assertEqual(str(values[0]), "8")
        self.assertEqual(report.invalid_hex_binary_literals_downgraded, 1)

    def test_existing_generic_uri_is_reminted(self) -> None:
        graph = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            ex:TMOPERATION_1 a ex:TareaMantenimiento ;
                ex:identificador "TMOPERATION = 1" ;
                ex:textoExtracto "Coger una herramienta del almacén." .
            """
        )

        sanitized, _ = sanitize_abox_graph(graph, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        subjects = list(sanitized.subjects(RDF.type, EX.TareaMantenimiento))
        self.assertEqual(len(subjects), 1)
        self.assertNotEqual(str(subjects[0]), str(EX.TMOPERATION_1))

    def test_existing_generic_uri_splits_by_type_context(self) -> None:
        graph_one = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            ex:TMOPERATION_1 a ex:TareaMantenimiento ;
                ex:identificador "TMOPERATION = 1" ;
                ex:textoExtracto "Coger una herramienta del almacén." .
            """
        )
        graph_two = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            ex:TMOPERATION_1 a ex:Parametro ;
                ex:identificador "1" ;
                ex:textoExtracto "TMOPERATION=1" .
            """
        )

        sanitized_one, _ = sanitize_abox_graph(graph_one, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        sanitized_two, _ = sanitize_abox_graph(graph_two, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        uri_one = next(sanitized_one.subjects(RDF.type, EX.TareaMantenimiento))
        uri_two = next(sanitized_two.subjects(RDF.type, EX.Parametro))
        self.assertNotEqual(str(uri_one), str(uri_two))

    def test_existing_generic_marca_uri_splits_parametro_and_interfaz(self) -> None:
        graph_one = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:MarcaGRTOSPDL a ex:InterfazUsuario ;
                rdfs:label "Marca GRTOSPDL" ;
                ex:identificador "GRTOSPDL" ;
                ex:textoExtracto "Marca GRTOSPDL al gestor." .
            """
        )
        graph_two = load_graph_from_text(
            """
            @prefix ex: <https://vocab.cfaa.eus/broaching/> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            ex:MarcaGRTOSPDL a ex:Parametro ;
                rdfs:label "Marca GRTOSPDL (M[1108])" ;
                ex:identificador "M[1108]" ;
                ex:textoExtracto "V.PLC.M[1108]=1 ; Marca GRTOSPDL al gestor." .
            """
        )

        sanitized_one, _ = sanitize_abox_graph(graph_one, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        sanitized_two, _ = sanitize_abox_graph(graph_two, tbox_graph=self.tbox_graph, mint_registry=self.registry)
        uri_one = next(sanitized_one.subjects(RDF.type, EX.InterfazUsuario))
        uri_two = next(sanitized_two.subjects(RDF.type, EX.Parametro))
        self.assertNotEqual(str(uri_one), str(EX.MarcaGRTOSPDL))
        self.assertNotEqual(str(uri_two), str(EX.MarcaGRTOSPDL))
        self.assertNotEqual(str(uri_one), str(uri_two))

    def test_extractor_integration_sanitizes_generated_ttl(self) -> None:
        chunk_text = "Texto de chunk completo que no debe quedar como extracto tal cual."
        ttl = """
        @prefix ex: <https://vocab.cfaa.eus/broaching/> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        <file:///tmp/artifact> ex:tieneComponente ex:SistemaCNC .
        ex:SistemaCNC a ex:Sistema ;
            ex:tieneComponente [
                a ex:ComponenteElectrico, ex:Componente ;
                rdfs:label "Motor principal" ;
                ex:textoExtracto "Texto de chunk completo que no debe quedar como extracto tal cual."
            ] .
        """

        sanitized_ttl, _ = sanitize_generated_ttl(
            ttl,
            tbox_graph=self.tbox_graph,
            source_chunk_text=chunk_text,
            mint_registry=self.registry,
        )
        sanitized = parse_ttl_graph(sanitized_ttl)
        self.assertNotIn("file:///", sanitized_ttl)
        component = next(obj for obj in sanitized.objects(EX.SistemaCNC, EX.tieneComponente) if isinstance(obj, URIRef))
        self.assertEqual({obj for obj in sanitized.objects(component, RDF.type)}, {EX.ComponenteElectrico})
        self.assertEqual(list(sanitized.objects(component, EX.textoExtracto)), [])

    def test_non_informative_chunk_is_detected(self) -> None:
        self.assertTrue(
            es_chunk_no_informativo(
                {
                    "texto_fuente": "8 8.",
                    "paginas": "[541]",
                    "seccion": "SIMULAR UN TECLADO DESDE EL",
                }
            )
        )
        self.assertTrue(es_chunk_no_informativo({"texto_fuente": "9"}))
        self.assertFalse(es_chunk_no_informativo({"texto_fuente": "El motor principal mueve el conjunto."}))

    def test_non_informative_chunk_placeholder_keeps_traceability(self) -> None:
        chunk = {
            "texto_fuente": "9",
            "paginas": "[608]",
            "seccion": "0.1632, 0.0904, -0.0028",
        }
        ttl = construir_ttl_chunk_no_informativo(chunk)
        sanitized_ttl, _ = sanitize_generated_ttl(
            ttl,
            tbox_graph=self.tbox_graph,
            source_chunk_text=chunk["texto_fuente"],
            mint_registry=self.registry,
        )
        semantic_result = validate_ttl_text_semantics(
            sanitized_ttl,
            vocabulary=load_semantic_vocabulary(),
        )
        self.assertTrue(semantic_result.ok)
        self.assertEqual(semantic_result.subjects_without_traceability, 0)


if __name__ == "__main__":
    unittest.main()
