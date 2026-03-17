from pathlib import Path
from rdflib import Graph, RDFS, OWL

TBOX_PATH = Path("data/processed/ontology_aligned.ttl")

def condensar_esquema():
    g = Graph()
    g.parse(TBOX_PATH, format="turtle")
    
    esquema_condensado = []
    
    # Extraer ObjectProperties (Relaciones entre nodos)
    for prop in g.subjects(RDFS.domain, None):
        dominio = g.value(prop, RDFS.domain)
        rango = g.value(prop, RDFS.range)
        
        # Limpiar URIs para lectura del LLM
        p_name = str(prop).split("#")[-1].split("/")[-1]
        d_name = str(dominio).split("#")[-1].split("/")[-1] if dominio else "Any"
        r_name = str(rango).split("#")[-1].split("/")[-1] if rango else "Any"
        
        # Omitir nodos anónimos (BNode) que ensucian el prompt
        if "BNode" not in str(type(dominio)) and "BNode" not in str(type(rango)):
            esquema_condensado.append(f"{d_name} -> {p_name} -> {r_name}")

    # Guardar para inyectar en el prompt
    output_path = Path("data/processed/schema_condensed.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(set(esquema_condensado))))
        
    print(f"Esquema condensado generado en {output_path}")

if __name__ == "__main__":
    condensar_esquema()