from __future__ import annotations

import re
import unicodedata

SHARED_TECHNICAL_SURFACE_REPLACEMENTS: list[tuple[str, str]] = [
    ("inspeccion de herramienta", "tool inspection"),
    ("busqueda de referencia", "home search"),
    ("tabla de utillajes", "fixture table"),
    ("modo utilidades", "utilities mode"),
    ("decalajes de cero absolutos", "absolute zero offsets"),
    ("decalajes de cero", "zero offsets"),
    ("tabla de parametros comunes", "common parameters table"),
    ("parametros comunes", "common parameters"),
    ("cero pieza", "part zero"),
    ("cinematica de la mesa", "table kinematics"),
    ("cinematica", "kinematics"),
    ("husillo maestro", "master spindle"),
    ("modo de bucle abierto", "open loop mode"),
    ("palpado", "probing"),
    ("hacer contacto", "making contact"),
    ("no hacer contacto", "not making contact"),
    ("simulacion de trayectoria teorica", "theoretical travel simulation"),
    ("trayectoria teorica", "theoretical travel"),
    ("plano principal", "main plane"),
    ("plato divisor", "rotary table"),
    ("ayuda del cnc", "cnc help"),
    ("modo mdi/mda", "mdi/mda mode"),
    ("tecla help", "help key"),
    ("tecla focus", "focus key"),
    ("tecla next", "next key"),
    ("tecla back", "back key"),
    ("tecla stop", "stop key"),
    ("tecla start", "start key"),
    ("tecla zero", "zero key"),
    ("tecla de rapido", "rapid key"),
    ("panel jog", "jog panel"),
    ("menu vertical de softkeys", "vertical softkey menu"),
    ("selector set-up", "set-up selector"),
    ("apertura puertas", "doors open"),
    ("columna de atributos", "attributes column"),
    ("atributo modificable", "modifiable attribute"),
    ("atributo oculto", "hidden attribute"),
    ("ficheros seleccionados", "selected files"),
    ("programa pieza", "part-program"),
    ("decalajes de sujecion", "clamp offsets"),
    ("todos los canales", "all channels"),
    ("funcion matematica", "mathematical function"),
    ("funcion auxiliar", "auxiliary function"),
    ("funcion preparatoria", "preparatory function"),
    ("funcion g", "g function"),
    ("funcion m", "m function"),
    ("codigo g", "g code"),
    ("sentido antihorario", "counterclockwise"),
    ("mecanizado multiple", "multiple machining"),
    ("patron rectangular", "rectangular pattern"),
    ("taladrado profundo", "deep-hole drilling"),
    ("calibracion semiautomatica", "semi-automatic calibration"),
    ("calibracion manual", "manual calibration"),
    ("movimiento de palpado", "probing movement"),
    ("modelo de torno en plano", "lathe model plane"),
    ("modelo de fresadora", "milling model"),
    ("distancia incremental", "incremental distance"),
    ("mandos manuales", "manual controls"),
    ("eje z", "z axis"),
    ("eje c", "c axis"),
    ("borrar el programa", "erase the program"),
    ("simulacion", "simulation"),
]


def normalize_for_matching(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    text = re.sub(r"[^a-z0-9@/_\-\+#\\\[\]\.]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonicalize_technical_surface(text: str) -> str:
    normalized = normalize_for_matching(text)
    for source, target in SHARED_TECHNICAL_SURFACE_REPLACEMENTS:
        normalized = normalized.replace(source, target)
    return re.sub(r"\s+", " ", normalized).strip()