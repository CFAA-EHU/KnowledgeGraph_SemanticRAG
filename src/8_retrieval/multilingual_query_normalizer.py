from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
INGESTION_DIR = REPO_ROOT / "src" / "1_ingestion"
if str(INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(INGESTION_DIR))

from artifact_contracts import MULTILINGUAL_LEXICON_PATH
from language_utils import detect_language, normalize_text

FULL_QUESTION_OVERRIDES = {
    "what maintenance plan does the machine safety system require": "que plan de mantenimiento requiere el sistema de seguridad de la maquina",
    "which directive does the external broaching machine comply with": "que directiva cumple la maquina de brochado exterior",
    "which figure shows the information that appears in the manual headers and footers": "que figura muestra la informacion que aparece en los encabezados y pies de pagina del manual",
    "what is the contact email for ekin indicated in the manual": "cual es el correo electronico de contacto de ekin indicado en el manual",
    "where is the address of ekin mentioned in the manual": "donde se encuentra la direccion de la empresa ekin mencionada en el manual",
    "who should be consulted in case of doubts about machine safety": "a quien se debe consultar en caso de dudas sobre la seguridad de la maquina",
    "what type of spare parts must be used according to the manual": "que tipo de piezas de recambio deben emplearse segun el manual",
    "according to which directive is the ce declaration of conformity for machinery made": "segun que directiva se realiza la declaracion ce de conformidad sobre maquinas",
}

PHRASE_REPLACEMENTS = [
    ("customer support department", "departamento de asistencia al cliente"),
    ("customer service department", "departamento de asistencia al cliente"),
    ("machine safety system", "sistema de seguridad de la maquina"),
    ("maintenance plan", "plan de mantenimiento"),
    ("external broaching machine", "maquina de brochado exterior"),
    ("broaching machine", "maquina de brochado"),
    ("manual headers and footers", "encabezados y pies de pagina del manual"),
    ("headers and footers", "encabezados y pies de pagina"),
    ("spare parts", "piezas de recambio"),
    ("original spare parts", "piezas de recambio originales"),
    ("contact email", "correo electronico de contacto"),
    ("email", "correo electronico"),
    ("e mail", "correo electronico"),
    ("address", "direccion"),
    ("which figure", "que figura"),
    ("what figure", "que figura"),
    ("which directive", "que directiva"),
    ("what directive", "que directiva"),
    ("what type of", "que tipo de"),
    ("where is", "donde se encuentra"),
    ("what is", "cual es"),
    ("who should be consulted", "a quien se debe consultar"),
    ("in case of doubts", "en caso de dudas"),
    ("about machine safety", "sobre la seguridad de la maquina"),
    ("according to", "segun"),
    ("ce declaration", "declaracion ce"),
    ("conformity", "conformidad"),
    ("machinery", "maquinas"),
    ("monitor and keyboard", "monitor y teclado"),
    ("monitor & keyboard", "monitor y teclado"),
    ("keyboard shortcuts", "atajos de teclado"),
    ("jog panel", "panel jog"),
    ("work modes", "modos de trabajo"),
    ("work mode", "modo de trabajo"),
    ("automatic mode", "modo automatico"),
    ("jog mode", "modo jog"),
    ("mdi/mda mode", "modo mdi/mda"),
    ("home search", "busqueda de referencia"),
    ("search reference", "busqueda de referencia"),
    ("homing", "busqueda de referencia"),
    ("coordinate preset", "preset de coordenadas"),
    ("feed rate", "avance"),
    ("feedrate", "avance"),
    ("spindle speed", "velocidad del husillo"),
    ("cycle start", "inicio de ciclo"),
    ("cycle stop", "parada de ciclo"),
    ("focus key", "tecla focus"),
    ("next key", "tecla next"),
    ("back key", "tecla back"),
    ("help key", "tecla help"),
    ("start key", "tecla start"),
    ("stop key", "tecla stop"),
    ("reset key", "tecla reset"),
    ("zero key", "tecla zero"),
    ("what key", "que tecla"),
    ("which key", "que tecla"),
    ("what does", "para que sirve"),
    ("what must be pressed", "que se debe pulsar"),
    ("which keys are used", "que teclas se utilizan"),
]

ANCHOR_GROUP_RULES = {
    "mdi_mda": [
        "mdi/mda",
        "mdi mda",
        "mdi",
        "mda",
        "modo mdi/mda",
        "programa interrumpido",
        "interrupted program",
        "active conditions",
        "condiciones activas",
    ],
    "canned_cycles": [
        "ciclo fijo",
        "canned cycle",
        "deep-hole drilling",
        "taladrado profundo",
        "multiple machining",
        "mecanizado multiple",
        "patron rectangular",
        "rectangular pattern",
    ],
    "tool_calibration": [
        "semi-automatic calibration",
        "calibracion semiautomatica",
        "manual calibration",
        "calibracion manual",
        "probing movement",
        "movimiento de palpado",
        "lathe model plane",
        "modelo de torno en plano",
        "milling model",
        "modelo de fresadora",
        "tool calibration",
        "calibracion de herramienta",
    ],
    "utilities_and_file_protection": [
        "utilities mode",
        "modo utilidades",
        "mode utilities",
        "file protection",
        "proteger un archivo",
        "modifiable attribute",
        "atributo modificable",
        "hidden attribute",
        "atributo oculto",
        "-m-",
        "-h-",
        "edisimu",
    ],
    "simulation": [
        "simulated execution",
        "ejecucion simulada",
        "simulation",
        "simulacion",
        "theoretical travel",
        "trayectoria teorica",
        "main plane",
        "plano principal",
        "plc",
    ],
    "tool_inspection": [
        "tool inspection",
        "inspeccion de herramienta",
        "vertical softkey menu",
        "menu vertical de softkeys",
        "stop key",
        "tecla stop",
    ],
    "jog_and_home": [
        "jog",
        "panel jog",
        "rapid key",
        "tecla de rapido",
        "home search",
        "busqueda de referencia",
        "zero key",
        "tecla zero",
        "manual controls",
        "mandos manuales",
        "incremental distance",
        "distancia incremental",
        "z axis",
        "eje z",
    ],
    "math_and_high_level": [
        "high level language",
        "instruccion de alto nivel",
        "alto nivel",
        "#servo off",
        "#master",
        "#kinorg",
        "#kin id",
        "fup",
        "funcion matematica",
        "mathematical function",
        "entero mas uno",
        "integer plus one",
        "cero pieza",
        "current part zero",
        "cinematica de la mesa",
        "table kinematics",
        "selecciona una cinematica",
        "selects a kinematics",
    ],
    "g_m_functions": [
        "g04",
        "g83",
        "g100",
        "g103",
        "g161",
        "m04",
        "funcion g",
        "funcion m",
        "codigo g",
        "auxiliary function",
        "funcion auxiliar",
        "preparatory function",
        "sentido antihorario",
        "counterclockwise",
        "probing",
        "palpado",
        "making contact",
        "hacer contacto",
        "not making contact",
        "no hacer contacto",
    ],
    "fixture_and_offsets": [
        "fixture table",
        "tabla de utillajes",
        "clamp offsets",
        "decalajes de sujecion",
        "common parameters",
        "parametros comunes",
        "g54",
        "g55",
        "g56",
        "g57",
        "g58",
        "g59",
    ],
    "syntax": [
        "syntax check",
        "analisis de sintaxis",
        "lenguaje cnc 8055",
        "8055 cnc language",
    ],
    "machine_c_axis_context": [
        "plato divisor",
        "rotary table",
        "eje c",
        "c axis",
        "#cax",
    ],
    "machine_safety_to_cnc_operation": [
        "set-up",
        "set up",
        "selector de set-up",
        "operator panel",
        "panel operador",
        "apertura puertas",
        "doors open",
        "puertas abiertas",
    ],
    "machine_program_recovery": [
        "emergency",
        "emergencia",
        "restaurar el sistema",
        "restore the system",
        "interrumpiendo un ciclo",
        "interrupting a machining cycle",
    ],
    "machine_offsets_and_parameters": [
        "all channels",
        "todos los canales",
        "parameter table",
        "tabla de parametros",
        "arithmetic parameter",
        "parametro aritmetico",
        "zero offsets",
        "decalajes de cero",
        "absolute zero offsets",
        "parametros comunes",
        "common parameters",
    ],
    "machine_axis_motion": [
        "carro porta-piezas",
        "carriage",
        "z axis",
        "eje z",
        "incremental distance",
        "distancia incremental",
        "manual controls",
        "mandos manuales",
    ],
    "machine_program_storage": [
        "c fagorcnc users prg",
        "users prg",
        "broaching program",
        "programa de brochado",
    ],
    "machine_utilities_navigation": [
        "ctrl + f12",
        "[ctrl] + [f12]",
        "delete",
        "borrar",
        "programa de brochado",
        "broaching program",
    ],
}

TECHNICAL_TOKEN_PATTERNS = {
    "mdi_mda": r"\bmdi(?:/mda)?\b|\bmda\b",
    "g04": r"\bg0?4\b",
    "g83": r"\bg83\b",
    "g100": r"\bg100\b",
    "g103": r"\bg103\b",
    "g161": r"\bg161\b",
    "g54_g59": r"\bg5[4-9]\b",
    "m04": r"\bm0?4\b",
    "q10.013": r"\bq10(?:[._])?013\b",
    "#servo off": r"#servo\s+off",
    "#master": r"#master\b",
    "#kinorg": r"#kinorg\b",
    "#kin id": r"#kin\s+id\b",
    "#cax": r"#cax\b",
    "fup": r"\bfup\b",
    "ctrl+f12": r"\[?\s*ctrl\s*\]?\s*\+?\s*\[?\s*f12\s*\]?",
}


@lru_cache(maxsize=1)
def load_multilingual_lexicon(path: str = str(MULTILINGUAL_LEXICON_PATH)) -> dict[str, Any]:
    lexicon_path = Path(path)
    if not lexicon_path.exists():
        return {"entries": [], "surface_index": {}}
    payload = json.loads(lexicon_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"entries": [], "surface_index": {}}


def _repair_mojibake(text: str) -> str:
    repaired = text or ""
    for _ in range(3):
        if "Ã" not in repaired and "Â" not in repaired:
            break
        try:
            candidate = repaired.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if candidate == repaired:
            break
        repaired = candidate
    return repaired


def _replace_phrases(question: str) -> str:
    repaired = _repair_mojibake(question)
    normalized = normalize_text(repaired)
    if normalized in FULL_QUESTION_OVERRIDES:
        return FULL_QUESTION_OVERRIDES[normalized]
    replaced = normalized
    for source, target in PHRASE_REPLACEMENTS:
        replaced = re.sub(rf"\b{re.escape(source)}\b", target, replaced)
    return re.sub(r"\s+", " ", replaced).strip()


def _surface_should_match(surface: str) -> bool:
    if not surface:
        return False
    if len(surface) >= 3:
        return True
    return bool(re.search(r"[#\d\[\]+/-]", surface))


def _surface_regex(surface: str) -> str:
    escaped = re.escape(surface)
    if re.search(r"[#\d\[\]+/-]", surface):
        return escaped
    return rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"


def _lexicon_hits(question: str, lexicon: dict[str, Any]) -> list[dict[str, Any]]:
    normalized_question = normalize_text(_repair_mojibake(question))
    hits: list[dict[str, Any]] = []
    surface_index = lexicon.get("surface_index", {})
    for surface, candidates in surface_index.items():
        if not isinstance(surface, str) or not _surface_should_match(surface):
            continue
        if not re.search(_surface_regex(normalize_text(surface)), normalized_question):
            continue
        filtered_candidates = []
        for candidate in candidates[:6]:
            entity_type = normalize_text(str(candidate.get("entity_type", "")))
            if entity_type in {"objectproperty", "datatypeproperty", "class"}:
                continue
            filtered_candidates.append(candidate)
        if filtered_candidates:
            hits.append({"surface": surface, "candidates": filtered_candidates[:3]})
    hits.sort(key=lambda item: (len(normalize_text(item["surface"])), len(item["candidates"])), reverse=True)
    deduped: list[dict[str, Any]] = []
    seen_surfaces: set[str] = set()
    for hit in hits:
        surface = normalize_text(hit["surface"])
        if surface in seen_surfaces:
            continue
        seen_surfaces.add(surface)
        deduped.append(hit)
        if len(deduped) >= 8:
            break
    return deduped


def _extract_anchor_groups(question: str) -> list[str]:
    normalized = normalize_text(question)
    groups: list[str] = []
    for group_id, phrases in ANCHOR_GROUP_RULES.items():
        if any(phrase in normalized for phrase in phrases):
            groups.append(group_id)
    return groups


def _extract_technical_tokens(question: str) -> list[str]:
    normalized = normalize_text(question)
    tokens: list[str] = []
    for token, pattern in TECHNICAL_TOKEN_PATTERNS.items():
        if re.search(pattern, normalized):
            tokens.append(token)
    return tokens


def normalize_question(question: str) -> dict[str, Any]:
    repaired_question = _repair_mojibake(question)
    language, confidence = detect_language(repaired_question)
    lexicon = load_multilingual_lexicon()
    planner_question = _replace_phrases(repaired_question) if language == "en" else _replace_phrases(repaired_question)
    hits = _lexicon_hits(planner_question, lexicon)
    if not hits:
        hits = _lexicon_hits(repaired_question, lexicon)
    anchor_groups = _extract_anchor_groups(planner_question)
    technical_tokens = _extract_technical_tokens(planner_question)
    return {
        "question_language": language,
        "question_language_confidence": round(confidence, 4),
        "normalized_question": planner_question,
        "planner_question": planner_question,
        "multilingual_lexicon_hits": hits,
        "anchor_groups": anchor_groups,
        "technical_tokens": technical_tokens,
        "repaired_question": repaired_question,
    }
