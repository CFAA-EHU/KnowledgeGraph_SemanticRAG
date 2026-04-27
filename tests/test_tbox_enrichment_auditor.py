from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import OWL, RDF, RDFS

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
EXTRACTION_DIR = REPO_ROOT / "src" / "6_extraction"
if str(EXTRACTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTION_DIR))

from tbox_enrichment_auditor import build_tbox_enrichment_evidence

EX = Namespace("https://vocab.cfaa.eus/broaching/")


class TboxEnrichmentAuditorTests(unittest.TestCase):
    def test_builds_evidence_without_creating_classes(self) -> None:
        tbox = Graph()
        for class_uri in (EX.Sistema, EX.Componente, EX.Manual, EX.Maquina, EX.Directiva, EX.Empresa):
            tbox.add((class_uri, RDF.type, OWL.Class))
        tbox.add((EX.tieneComponente, RDF.type, OWL.ObjectProperty))
        tbox.add((EX.tieneComponente, RDFS.domain, EX.Sistema))
        tbox.add((EX.tieneComponente, RDFS.range, EX.Componente))

        abox = Graph()
        abox.add((EX.SistemaCNC, RDF.type, EX.Sistema))
        abox.add((EX.SensorX, RDF.type, EX.Componente))
        abox.add((EX.SistemaCNC, EX.tieneComponente, EX.SensorX))

        with tempfile.TemporaryDirectory() as tmpdir:
            tbox_path = Path(tmpdir) / "tbox.ttl"
            abox_path = Path(tmpdir) / "abox.ttl"
            tbox.serialize(destination=tbox_path, format="turtle")
            abox.serialize(destination=abox_path, format="turtle")

            evidence = build_tbox_enrichment_evidence(abox_path=abox_path, tbox_path=tbox_path)

        self.assertEqual(evidence["summary"]["declared_class_count"], 6)
        self.assertEqual(evidence["classes_with_individuals"][0]["class"], "Sistema")
        self.assertEqual(evidence["object_properties_used"], [{"property": "tieneComponente", "count": 1}])
        applicable_disjoints = {
            (item["left_class"], item["right_class"])
            for item in evidence["disjointness_candidates"]
            if item["status"] == "applicable"
        }
        self.assertIn(("Maquina", "Manual"), applicable_disjoints)
        self.assertIn(("Empresa", "Directiva"), applicable_disjoints)


if __name__ == "__main__":
    unittest.main()
