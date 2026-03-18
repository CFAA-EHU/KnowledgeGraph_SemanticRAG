import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rdflib import Graph


def validate_ttl_text(ttl_data: str) -> tuple[bool, str | None]:
    ttl_text = ttl_data.strip()
    if not ttl_text:
        return False, "TTL vacio."
    try:
        graph = Graph()
        graph.parse(data=ttl_text, format="turtle")
        return True, None
    except Exception as exc:
        return False, str(exc)


def validate_ttl_file(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, f"Archivo TTL no encontrado: {path}"
    return validate_ttl_text(path.read_text(encoding='utf-8'))
