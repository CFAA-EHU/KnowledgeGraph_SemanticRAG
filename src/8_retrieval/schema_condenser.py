import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rdflib import Graph, RDFS, OWL

from artifact_contracts import OPERATIONAL_TBOX_PATH, SCHEMA_CONDENSED_PATH

TBOX_PATH = OPERATIONAL_TBOX_PATH

def condensar_esquema():
    g = Graph()
    g.parse(TBOX_PATH, format="turtle")

    esquema_condensado = []

    for prop in g.subjects(RDFS.domain, None):
        dominio = g.value(prop, RDFS.domain)
        rango = g.value(prop, RDFS.range)

        p_name = str(prop).split("#")[-1].split("/")[-1]
        d_name = str(dominio).split("#")[-1].split("/")[-1] if dominio else "Any"
        r_name = str(rango).split("#")[-1].split("/")[-1] if rango else "Any"

        if "BNode" not in str(type(dominio)) and "BNode" not in str(type(rango)):
            esquema_condensado.append(f"{d_name} -> {p_name} -> {r_name}")

    with open(SCHEMA_CONDENSED_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(set(esquema_condensado))))

    print(f"Esquema condensado generado en {SCHEMA_CONDENSED_PATH}")

if __name__ == "__main__":
    condensar_esquema()
