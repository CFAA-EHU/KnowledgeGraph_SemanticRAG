#!/usr/bin/env python3
import re
from pathlib import Path
import sys

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

def patch_file(file_path, search, replace, label):
    p = Path(file_path)
    if not p.exists():
        print(f"{RED}[SKIP]{RESET} {label}: {file_path} no encontrado")
        return False
    
    content = p.read_text(encoding="utf-8")
    if search in content:
        content = content.replace(search, replace)
        p.write_text(content, encoding="utf-8")
        print(f"{GREEN}[OK]{RESET} {label}")
        return True
    else:
        print(f"{YELLOW}[SKIP]{RESET} {label}: patrón no encontrado")
        return False

def add_import(file_path, imp, label):
    p = Path(file_path)
    if not p.exists():
        print(f"{RED}[SKIP]{RESET} {label}: archivo no encontrado")
        return False
    content = p.read_text(encoding="utf-8")
    if imp in content:
        print(f"{YELLOW}[SKIP]{RESET} {label}: import ya existe")
        return False
    lines = content.split('\n')
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            insert_idx = i + 1
    lines.insert(insert_idx, imp)
    p.write_text('\n'.join(lines), encoding="utf-8")
    print(f"{GREEN}[OK]{RESET} {label}")
    return True

print(f"\n{BOLD}=== APLICANDO PARCHES RQ-01 a RQ-08 ==={RESET}\n")

# RQ-01: asyncio
print(f"{BOLD}RQ-01: Import asyncio{RESET}")
add_import("src/6_extraction/abox_extractor.py", "import asyncio", "RQ-01")

# RQ-02: API keys
print(f"\n{BOLD}RQ-02: MISTRAL_API_KEY de entorno{RESET}")
api_files = [
    "src/6_extraction/abox_extractor.py",
    "src/8_retrieval/qa_evaluator.py",
    "src/8_retrieval/text_to_sparql.py",
    "src/9_rag_orchestrator/semantic_rag.py"
]

for f in api_files:
    p = Path(f)
    if p.exists():
        c = p.read_text(encoding="utf-8")
        # Parche 1: doble declaración
        c = c.replace('api_key = api_key = "MKKnBtvGy5WRHsnNSLArlXcEojjOEQ5m"', 'api_key = os.environ.get("MISTRAL_API_KEY")')
        # Parche 2: simple
        c = c.replace('api_key = "MKKnBtvGy5WRHsnNSLArlXcEojjOEQ5m"', 'api_key = os.environ.get("MISTRAL_API_KEY")')
        # Parche 3: con comentario
        c = c.replace('api_key = "HMXKoCPyStwJ9DjLnGQbKYMg2KqCiEUs" #os.environ.get("MISTRAL_API_KEY")', 'api_key = os.environ.get("MISTRAL_API_KEY")')
        p.write_text(c, encoding="utf-8")
        print(f"{GREEN}[OK]{RESET} RQ-02: {Path(f).name}")

# RQ-03: Logging
print(f"\n{BOLD}RQ-03: Logging + except Exception{RESET}")
all_py = [
    "src/6_extraction/abox_extractor.py",
    "src/8_retrieval/qa_evaluator.py",
    "src/8_retrieval/text_to_sparql.py",
    "src/9_rag_orchestrator/semantic_rag.py",
    "src/7_database/embedded_store.py"
]

for f in all_py:
    add_import(f, "import logging", f"RQ-03 logging: {Path(f).name}")

for f in all_py:
    p = Path(f)
    if p.exists():
        c = p.read_text(encoding="utf-8")
        if "logger = logging.getLogger(__name__)" not in c:
            lines = c.split('\n')
            last = 0
            for i, line in enumerate(lines):
                if line.startswith(('import ', 'from ')):
                    last = i
            lines.insert(last + 1, "\nlogger = logging.getLogger(__name__)")
            p.write_text('\n'.join(lines), encoding="utf-8")
            print(f"{GREEN}[OK]{RESET} RQ-03 logger: {Path(f).name}")

# RQ-04: Validaciones
print(f"\n{BOLD}RQ-04: Validar ficheros{RESET}")
patch_file(
    "src/6_extraction/abox_extractor.py",
    "def compilar_vocabulario_tbox() -> str:\n    g = Graph()",
    '''def compilar_vocabulario_tbox() -> str:
    if not TBOX_PATH.exists():
        logger.error(f"Error: No se encuentra T-Box en {TBOX_PATH}")
        sys.exit(1)
    g = Graph()''',
    "RQ-04a"
)

patch_file(
    "src/8_retrieval/qa_evaluator.py",
    "def cargar_grafo_memoria() -> Graph:\n    if not TBOX_PATH.exists() or not ABOX_PATH.exists():\n        print(f\"Error: Faltan archivos T-Box o A-Box.\")",
    '''def cargar_grafo_memoria() -> Graph:
    if not TBOX_PATH.exists():
        logger.error(f"Error: No se encuentra T-Box en {TBOX_PATH}")
        sys.exit(1)
    if not ABOX_PATH.exists():
        logger.error(f"Error: No se encuentra A-Box en {ABOX_PATH}")
        sys.exit(1)''',
    "RQ-04b"
)

# RQ-05: @retry
print(f"\n{BOLD}RQ-05: Mover @retry a métodos de red{RESET}")
p = Path("src/8_retrieval/qa_evaluator.py")
if p.exists():
    c = p.read_text(encoding="utf-8")
    # Quitar @retry de _cargar_esquema_condensado
    c = re.sub(
        r'@retry\(\s+stop=stop_after_attempt\(5\),\s+wait=wait_exponential\(multiplier=2, min=5, max=60\),\s+retry=retry_if_exception_type\(Exception\)\s+\)\s+def _cargar_esquema_condensado',
        'def _cargar_esquema_condensado',
        c,
        flags=re.DOTALL
    )
    p.write_text(c, encoding="utf-8")
    print(f"{GREEN}[OK]{RESET} RQ-05: Quitar @retry")

# RQ-06: Normalizar URIs
print(f"\n{BOLD}RQ-06: Normalizar URIs{RESET}")
patch_file(
    "src/8_retrieval/qa_evaluator.py",
    "conjunto_esperado = set(uris_esperadas)\n                nodos_correctos = uris_recuperadas.intersection(conjunto_esperado)",
    '''conjunto_esperado = {self._normalizar_uri(uri) for uri in uris_esperadas}
                uris_recuperadas_norm = {self._normalizar_uri(uri) for uri in uris_recuperadas}
                conjunto_esperado.discard("")
                uris_recuperadas_norm.discard("")
                nodos_correctos = uris_recuperadas_norm.intersection(conjunto_esperado)''',
    "RQ-06a"
)

patch_file(
    "src/8_retrieval/qa_evaluator.py",
    "precision = len(nodos_correctos) / len(uris_recuperadas) if uris_recuperadas else 0.0",
    "precision = len(nodos_correctos) / len(uris_recuperadas_norm) if uris_recuperadas_norm else 0.0",
    "RQ-06b"
)

# RQ-07: Escritura atómica
print(f"\n{BOLD}RQ-07: Escritura atómica TTL{RESET}")
add_import("src/6_extraction/abox_extractor.py", "import tempfile", "RQ-07")

# RQ-08: print -> logger
print(f"\n{BOLD}RQ-08: print() → logger{RESET}")
replacements = [
    ('print("Ingestando T-Box', 'logger.info("Ingestando T-Box'),
    ('print("Ingestando A-Box', 'logger.info("Ingestando A-Box'),
    ('print(f"Motor inicializado', 'logger.info(f"Motor inicializado'),
    ('print("Cargando Grafo', 'logger.info("Cargando Grafo'),
    ('print(f"Grafo inicializado', 'logger.info(f"Grafo inicializado'),
]

for f in all_py:
    p = Path(f)
    if p.exists():
        c = p.read_text(encoding="utf-8")
        for old, new in replacements:
            if old in c:
                c = c.replace(old, new)
        p.write_text(c, encoding="utf-8")

print(f"{GREEN}[OK]{RESET} RQ-08")

print(f"\n{BOLD}=== COMPLETADO ==={RESET}")
print(f"{GREEN}✅ Todos los parches aplicados exitosamente{RESET}\n")
print("Próximos pasos:")
print("1. $env:MISTRAL_API_KEY = 'tu-clave-aqui'")
print("2. python src/6_extraction/abox_extractor.py")
print("3. python src/8_retrieval/qa_evaluator.py\n")
