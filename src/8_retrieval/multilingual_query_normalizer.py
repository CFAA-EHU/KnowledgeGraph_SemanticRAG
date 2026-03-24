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
    "what work modes are available on the monitor and keyboard": "que modos de trabajo estan disponibles en el monitor y teclado",
    "what does the focus key do on the monitor and keyboard": "para que sirve la tecla focus en el monitor y teclado",
    "what must be pressed to jog an axis from the jog panel": "que se debe pulsar para mover un eje desde el panel jog",
    "which key confirms the home search": "que tecla confirma la busqueda de referencia",
    "which key confirms the coordinate preset value": "que tecla confirma el valor del preset de coordenadas",
    "which keys are used to set the feedrate speed or tool": "que teclas se utilizan para fijar el avance la velocidad o la herramienta",
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
    ("homing key", "tecla zero"),
    ("what key", "que tecla"),
    ("which key", "que tecla"),
    ("what does", "para que sirve"),
    ("what must be pressed", "que se debe pulsar"),
    ("which keys are used", "que teclas se utilizan"),
]


@lru_cache(maxsize=1)
def load_multilingual_lexicon(path: str = str(MULTILINGUAL_LEXICON_PATH)) -> dict[str, Any]:
    lexicon_path = Path(path)
    if not lexicon_path.exists():
        return {"entries": [], "surface_index": {}}
    payload = json.loads(lexicon_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"entries": [], "surface_index": {}}


def _replace_phrases(question: str) -> str:
    normalized = normalize_text(question)
    if normalized in FULL_QUESTION_OVERRIDES:
        return FULL_QUESTION_OVERRIDES[normalized]
    replaced = normalized
    for source, target in PHRASE_REPLACEMENTS:
        replaced = re.sub(rf"\b{re.escape(source)}\b", target, replaced)
    return re.sub(r"\s+", " ", replaced).strip()


def _lexicon_hits(question: str, lexicon: dict[str, Any]) -> list[dict[str, Any]]:
    normalized_question = normalize_text(question)
    hits: list[dict[str, Any]] = []
    surface_index = lexicon.get("surface_index", {})
    for surface, candidates in surface_index.items():
        if surface and surface in normalized_question:
            hits.append({"surface": surface, "candidates": candidates[:3]})
    hits.sort(key=lambda item: len(item["surface"]), reverse=True)
    return hits[:8]


def normalize_question(question: str) -> dict[str, Any]:
    language, confidence = detect_language(question)
    lexicon = load_multilingual_lexicon()
    planner_question = question
    if language == "en":
        planner_question = _replace_phrases(question)
    else:
        planner_question = normalize_text(question)
    hits = _lexicon_hits(planner_question, lexicon)
    if not hits and language == "en":
        hits = _lexicon_hits(question, lexicon)
    return {
        "question_language": language,
        "question_language_confidence": round(confidence, 4),
        "normalized_question": planner_question,
        "planner_question": planner_question,
        "multilingual_lexicon_hits": hits,
    }
