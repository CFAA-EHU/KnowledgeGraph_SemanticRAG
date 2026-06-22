import sys
from pathlib import Path
from rdflib import Graph

INPUT_DIR = Path("data/processed/graphs/")
OUTPUT_FILE = Path("data/processed/ontology_merged.ttl")

def merge_graphs():
    if not INPUT_DIR.exists():
        print(f"Error: directory not found — {INPUT_DIR}")
        sys.exit(1)

    ttl_files = list(INPUT_DIR.glob("*.ttl"))
    if not ttl_files:
        print("Error: no TTL files to process.")
        sys.exit(1)

    unified_graph = Graph()
    successes = 0
    errors = 0

    print(f"Merging {len(ttl_files)} fragments ...")

    for ttl_file in ttl_files:
        try:
            temp_graph = Graph()
            temp_graph.parse(ttl_file, format="turtle")
            unified_graph += temp_graph
            successes += 1
        except Exception as e:
            print(f"Corruption detected in {ttl_file.name}: discarded. Details: {e}")
            errors += 1

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    unified_graph.serialize(destination=OUTPUT_FILE, format="turtle")

    print("-" * 40)
    print("MERGE SUMMARY")
    print("-" * 40)
    print(f"Fragments merged  : {successes}")
    print(f"Fragments corrupt : {errors}")
    print(f"Total triples     : {len(unified_graph)}")
    print(f"Output file       : {OUTPUT_FILE}")

if __name__ == "__main__":
    merge_graphs()
