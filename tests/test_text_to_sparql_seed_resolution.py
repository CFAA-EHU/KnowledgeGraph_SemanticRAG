import unittest
import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS

REPO_ROOT = Path(__file__).resolve().parents[1]
RETRIEVAL_DIR = REPO_ROOT / "src" / "8_retrieval"
if str(RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(RETRIEVAL_DIR))

from text_to_sparql import BASE_URI, reconcile_fixed_seed_uris


class FixedSeedResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = Graph()
        ex = BASE_URI
        self.identificador = URIRef(f"{ex}identificador")

        sistema = URIRef(f"{ex}SistemaSeguridadMaquinaBrochadoraEKIN")
        self.graph.add((sistema, RDF.type, URIRef(f"{ex}Sistema")))
        self.graph.add((sistema, RDFS.label, Literal("Sistema de seguridad de la máquina brochadora EKIN", lang="es")))

        empresa = URIRef(f"{ex}EKIN_S_Coop")
        self.graph.add((empresa, RDF.type, URIRef(f"{ex}Empresa")))
        self.graph.add((empresa, RDFS.label, Literal("EKIN S. Coop.")))

        kinid = URIRef(f"{ex}NumeroDeCinematicaDeCanalKINID")
        self.graph.add((kinid, RDF.type, URIRef(f"{ex}Parametro")))
        self.graph.add((kinid, RDFS.label, Literal("Parámetro máquina KINID", lang="es")))
        self.graph.add((kinid, self.identificador, Literal("KINID")))

        error_8026 = URIRef(f"{ex}Error_8026")
        self.graph.add((error_8026, RDF.type, URIRef(f"{ex}DiagnosticoFallo")))
        self.graph.add((error_8026, RDFS.label, Literal("Error 8026: Protección OEM activada", lang="es")))
        self.graph.add((error_8026, self.identificador, Literal("8026")))

    def test_resolves_known_alias_override(self) -> None:
        resolved = reconcile_fixed_seed_uris([f"{BASE_URI}SistemaSeguridadMaquina"], self.graph)
        self.assertEqual(resolved, [f"{BASE_URI}SistemaSeguridadMaquinaBrochadoraEKIN"])

    def test_resolves_company_seed_by_alias_map(self) -> None:
        resolved = reconcile_fixed_seed_uris([f"{BASE_URI}Empresa_EKIN_S_Coop"], self.graph)
        self.assertEqual(resolved, [f"{BASE_URI}EKIN_S_Coop"])

    def test_resolves_parameter_seed_by_identifier(self) -> None:
        resolved = reconcile_fixed_seed_uris([f"{BASE_URI}Parametro_KINID"], self.graph)
        self.assertEqual(resolved, [f"{BASE_URI}NumeroDeCinematicaDeCanalKINID"])

    def test_resolves_error_seed_by_numeric_code(self) -> None:
        resolved = reconcile_fixed_seed_uris([f"{BASE_URI}Alarma_8026"], self.graph)
        self.assertEqual(resolved, [f"{BASE_URI}Error_8026"])


if __name__ == "__main__":
    unittest.main()
