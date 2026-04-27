import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import argparse
import asyncio
import json
import os
import random
import re
from dataclasses import dataclass

from mistralai.client import Mistral
from rdflib import Graph

from artifact_contracts import (
    ABOX_CHUNKS_DIR,
    ABOX_DEBUG_DIR,
    ABOX_MINTED_ENTITY_REGISTRY_PATH,
    ABOX_MAX_LOCAL_RETRIES,
    ABOX_MICRO_BATCH_RECOVERY_BACKOFF_SECONDS,
    ABOX_MICRO_BATCH_RECOVERY_JITTER_RANGE,
    ABOX_MICRO_BATCH_RECOVERY_MAX_CONCURRENCY,
    ABOX_MICRO_BATCH_RECOVERY_MAX_RETRIES,
    ABOX_MICRO_BATCH_RECOVERY_REQUEST_SPACING_SECONDS,
    ABOX_RATE_LIMIT_DRAIN_BACKOFF_SECONDS,
    ABOX_RATE_LIMIT_DRAIN_JITTER_RANGE,
    ABOX_RATE_LIMIT_DRAIN_MAX_CONCURRENCY,
    ABOX_RATE_LIMIT_DRAIN_MAX_RETRIES,
    ABOX_RATE_LIMIT_DRAIN_REQUEST_SPACING_SECONDS,
    ABOX_RETRYABLE_ERROR_CAUSES,
    ABOX_RETRY_BACKOFF_SECONDS,
    ABOX_STANDARD_MAX_CONCURRENCY,
    OPERATIONAL_ABOX_INPUT_PATH,
    OPERATIONAL_ABOX_MANIFEST_PATH,
    OPERATIONAL_TBOX_PATH,
    hash_file_content,
    resolve_mistral_model_chain,
)
from abox_resume_policy import build_manifest_entry, determine_chunk_action, load_manifest, save_manifest
from abox_graph_sanitizer import load_mint_registry, sanitize_abox_graph, save_mint_registry, serialize_graph
from abox_semantic_validator import (
    load_semantic_vocabulary,
    validate_abox_graph,
    summarize_semantic_result,
    validate_ttl_file_semantics,
    validate_ttl_text_semantics,
)
from abox_ttl_validator import validate_ttl_file, validate_ttl_text

ABOX_INPUT_PATH = OPERATIONAL_ABOX_INPUT_PATH
MANIFEST_PATH = OPERATIONAL_ABOX_MANIFEST_PATH
TBOX_PATH = OPERATIONAL_TBOX_PATH
OUTPUT_DIR = ABOX_CHUNKS_DIR
DEBUG_DIR = ABOX_DEBUG_DIR
MODEL_CHAIN = resolve_mistral_model_chain()
PRIMARY_MODEL = MODEL_CHAIN[0]
BASE_URI = "https://vocab.cfaa.eus/broaching/"
ABOX_PROMPT_VERSION = "semantic-guardrails-v3"
EXTRACTION_MODE = "abox_from_text_chunk"
DEFAULT_MODE = "resume-compatible"
DEFAULT_RETRY_PROFILE = "standard"

client: Mistral | None = None


@dataclass(frozen=True)
class RetryProfile:
    name: str
    max_concurrency: int
    max_retries: int
    backoff_seconds: tuple[int, ...]
    jitter_range: tuple[float, float]
    request_spacing_seconds: float


@dataclass(frozen=True)
class ModelFallbackExhaustedError(Exception):
    error_cause: str
    error_message: str
    attempted_models: tuple[str, ...]
    last_model_name: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extraccion A-Box con reanudacion compatible por chunk.")
    parser.add_argument(
        "--mode",
        choices=["resume-compatible", "force-stale", "force-all"],
        default=DEFAULT_MODE,
        help="Politica de relanzamiento para la extraccion A-Box.",
    )
    parser.add_argument(
        "--chunk-ids",
        default="",
        help="Lista separada por comas de chunk_id a regenerar/validar para una corrida controlada.",
    )
    parser.add_argument(
        "--abox-input",
        type=Path,
        default=ABOX_INPUT_PATH,
        help="Ruta del A-Box input a procesar.",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=MANIFEST_PATH,
        help="Ruta del manifest de reanudacion A-Box.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directorio de salida para los fragmentos TTL A-Box.",
    )
    parser.add_argument(
        "--debug-dir",
        type=Path,
        default=DEBUG_DIR,
        help="Directorio de debug para fallos de extraccion A-Box.",
    )
    parser.add_argument(
        "--retry-profile",
        choices=["standard", "rate-limit-drain", "micro-batch-recovery"],
        default=DEFAULT_RETRY_PROFILE,
        help="Perfil de reintentos. micro-batch-recovery endurece el backoff para drenar pendientes residuales chunk a chunk.",
    )
    return parser.parse_args()


def parse_chunk_ids(raw_value: str) -> set[int]:
    if not raw_value.strip():
        return set()
    chunk_ids: set[int] = set()
    for item in raw_value.split(","):
        value = item.strip()
        if not value:
            continue
        chunk_ids.add(int(value))
    return chunk_ids


def get_client() -> Mistral:
    global client
    if client is None:
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise RuntimeError("Define la variable de entorno MISTRAL_API_KEY antes de ejecutar regeneraciones A-Box.")
        client = Mistral(api_key=api_key)
    return client


def get_model_chain() -> tuple[str, ...]:
    return MODEL_CHAIN


def compilar_vocabulario_tbox() -> str:
    g = Graph()
    g.parse(TBOX_PATH, format="turtle")
    clases, obj_props, data_props = set(), set(), set()
    for s, p, o in g:
        if "Class" in str(o):
            clases.add(str(s).split("/")[-1])
        elif "ObjectProperty" in str(o):
            obj_props.add(str(s).split("/")[-1])
        elif "DatatypeProperty" in str(o):
            data_props.add(str(s).split("/")[-1])
    return (
        f"- Clases permitidas: {', '.join(sorted(clases))}\n"
        f"- Propiedades de objeto permitidas: {', '.join(sorted(obj_props))}\n"
        f"- Propiedades de datos permitidas: {', '.join(sorted(data_props))}"
    )


def parse_ttl_graph(ttl_text: str) -> Graph:
    graph = Graph()
    graph.parse(data=ttl_text, format="turtle")
    return graph


def sanitize_generated_ttl(
    ttl_text: str,
    *,
    tbox_graph: Graph,
    source_chunk_text: str | None = None,
    mint_registry: dict[str, str] | None = None,
) -> tuple[str, dict]:
    graph = parse_ttl_graph(ttl_text)
    sanitized_graph, sanitization_result = sanitize_abox_graph(
        graph,
        tbox_graph=tbox_graph,
        source_chunk_text=source_chunk_text,
        mint_registry=mint_registry,
    )
    return serialize_graph(sanitized_graph), sanitization_result.to_manifest_summary()


def aislar_sintaxis_ttl(respuesta_llm: str) -> str:
    patron = r"`{3}(?:turtle|ttl)?\n(.*?)`{3}"
    match = re.search(patron, respuesta_llm, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else respuesta_llm.strip()


def es_chunk_pagina_en_blanco(chunk_data: dict) -> bool:
    texto = (chunk_data.get("texto_fuente") or "").strip().lower()
    return texto in {"pagina en blanco", "página en blanco", "blank page"}


def es_chunk_no_informativo(chunk_data: dict) -> bool:
    texto = " ".join((chunk_data.get("texto_fuente") or "").strip().split())
    if not texto:
        return True
    if es_chunk_pagina_en_blanco(chunk_data):
        return False
    if re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", texto):
        return False
    compact = re.sub(r"\s+", "", texto)
    return len(compact) <= 12 and bool(re.fullmatch(r"[\d\W_]+", compact))


def construir_ttl_pagina_en_blanco(chunk_data: dict) -> str:
    paginas = (chunk_data.get("paginas") or "sin_pagina").strip("[]")
    paginas_slug = re.sub(r"[^A-Za-z0-9_]+", "_", paginas).strip("_") or "sin_pagina"
    label = f"Página en blanco {chunk_data.get('paginas', '')}".strip()
    texto_extracto = chunk_data.get("texto_fuente", "PÁGINA EN BLANCO")
    return (
        f'@prefix ex: <{BASE_URI}> .\n'
        '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n\n'
        f'ex:PaginaEnBlanco_{paginas_slug} a ex:Pagina ;\n'
        f'    rdfs:label "{label}" ;\n'
        f'    ex:textoExtracto "{texto_extracto}" .\n'
    )


def construir_ttl_chunk_no_informativo(chunk_data: dict) -> str:
    paginas = (chunk_data.get("paginas") or "sin_pagina").strip("[]")
    paginas_slug = re.sub(r"[^A-Za-z0-9_]+", "_", paginas).strip("_") or "sin_pagina"
    seccion = " ".join((chunk_data.get("seccion") or "").split())
    label = f"Página {paginas} - fragmento no informativo".strip()
    if seccion:
        label = f"{label} ({seccion[:80]})"
    texto_extracto = f"Fragmento no informativo detectado en la página {paginas or 'sin página'}."
    return (
        f'@prefix ex: <{BASE_URI}> .\n'
        '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n\n'
        f'ex:PaginaNoInformativa_{paginas_slug} a ex:Pagina ;\n'
        f'    rdfs:label "{label}" ;\n'
        f'    ex:identificador "{paginas or "sin_pagina"}" ;\n'
        f'    ex:textoExtracto "{texto_extracto}" .\n'
    )


def garantizar_prefijos_obligatorios(ttl_text: str) -> str:
    ttl_limpio = ttl_text.strip()
    prefijos = []
    if not re.search(r"(?im)^(?:@prefix|PREFIX)\s+ex:\b", ttl_limpio):
        prefijos.append(f"@prefix ex: <{BASE_URI}> .")
    if "rdfs:" in ttl_limpio and not re.search(r"(?im)^(?:@prefix|PREFIX)\s+rdfs:\b", ttl_limpio):
        prefijos.append("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .")
    if "rdf:" in ttl_limpio and not re.search(r"(?im)^(?:@prefix|PREFIX)\s+rdf:\b", ttl_limpio):
        prefijos.append("@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
    if "xsd:" in ttl_limpio and not re.search(r"(?im)^(?:@prefix|PREFIX)\s+xsd:\b", ttl_limpio):
        prefijos.append("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .")
    if not prefijos:
        return ttl_limpio
    return "\n".join(prefijos + [ttl_limpio])


def normalizar_puntuacion_problematica(ttl_text: str) -> str:
    reemplazos = {
        "\u201c": "'",
        "\u201d": "'",
        "\u2018": "'",
        "\u2019": "'",
        "â€œ": "'",
        "â€\u009d": "'",
        "â€˜": "'",
        "â€™": "'",
        "Â·": "·",
        "Âº": "º",
    }
    ttl_normalizado = ttl_text
    for origen, destino in reemplazos.items():
        ttl_normalizado = ttl_normalizado.replace(origen, destino)
    return ttl_normalizado


def normalizar_hex_binary_invalidos(ttl_text: str) -> str:
    pattern = re.compile(r'"([^"\n]*)"\^\^xsd:hexBinary')

    def replacer(match: re.Match[str]) -> str:
        lexical = match.group(1).strip()
        normalized = lexical[1:] if lexical.startswith("$") else lexical
        normalized = normalized.replace(" ", "").upper()
        if normalized and len(normalized) % 2 == 0 and re.fullmatch(r"[0-9A-F]+", normalized):
            return f'"{normalized}"^^xsd:hexBinary'
        return f'"{lexical}"^^xsd:string'

    return pattern.sub(replacer, ttl_text)


def escapar_comillas_internas_en_literales(ttl_text: str) -> str:
    resultado: list[str] = []
    i = 0
    n = len(ttl_text)
    dentro_literal = False

    while i < n:
        actual = ttl_text[i]

        if not dentro_literal:
            if ttl_text.startswith('"""', i):
                fin = ttl_text.find('"""', i + 3)
                if fin == -1:
                    resultado.append(ttl_text[i:])
                    break
                resultado.append(ttl_text[i : fin + 3])
                i = fin + 3
                continue
            if actual == '"' and (i == 0 or ttl_text[i - 1] != "\\"):
                dentro_literal = True
            resultado.append(actual)
            i += 1
            continue

        if actual == '"' and (i == 0 or ttl_text[i - 1] != "\\"):
            siguiente = ttl_text[i + 1] if i + 1 < n else ""
            if siguiente in {"", ";", ",", ".", "@", "^", "]", ")"} or siguiente.isspace():
                resultado.append(actual)
                dentro_literal = False
            else:
                resultado.append('\\"')
            i += 1
            continue

        resultado.append(actual)
        i += 1

    return "".join(resultado)


def escapar_barras_invertidas_en_literales(ttl_text: str) -> str:
    resultado: list[str] = []
    i = 0
    n = len(ttl_text)
    estado = "outside"
    valid_simple_escapes = {'t', 'b', 'n', 'r', 'f', '"', "'", "\\"}

    def _is_hex_escape(start_index: int, length: int) -> bool:
        end_index = start_index + length
        if end_index > n:
            return False
        return all(char in "0123456789abcdefABCDEF" for char in ttl_text[start_index:end_index])

    while i < n:
        if estado == "outside":
            if ttl_text.startswith('"""', i):
                resultado.append('"""')
                estado = "long"
                i += 3
                continue
            if ttl_text[i] == '"' and (i == 0 or ttl_text[i - 1] != "\\"):
                resultado.append('"')
                estado = "short"
                i += 1
                continue
            resultado.append(ttl_text[i])
            i += 1
            continue

        if estado == "long" and ttl_text.startswith('"""', i):
            resultado.append('"""')
            estado = "outside"
            i += 3
            continue

        char = ttl_text[i]
        if char == "\\":
            next_char = ttl_text[i + 1] if i + 1 < n else ""
            if next_char and next_char in valid_simple_escapes:
                resultado.append("\\")
                resultado.append(next_char)
                i += 2
                continue
            if next_char == "u" and _is_hex_escape(i + 2, 4):
                resultado.append("\\u")
                resultado.extend(ttl_text[i + 2 : i + 6])
                i += 6
                continue
            if next_char == "U" and _is_hex_escape(i + 2, 8):
                resultado.append("\\U")
                resultado.extend(ttl_text[i + 2 : i + 10])
                i += 10
                continue
            resultado.append("\\\\")
            i += 1
            continue

        if estado == "short" and char in {"\n", "\r"}:
            resultado.append(" ")
            i += 1
            continue

        if estado == "short" and char == '"' and (i == 0 or ttl_text[i - 1] != "\\"):
            resultado.append('"')
            estado = "outside"
            i += 1
            continue

        resultado.append(char)
        i += 1

    return "".join(resultado)


def tipar_tablas_canonicas(ttl_text: str) -> str:
    patron = re.compile(
        r"(?m)^(ex:(?:Tabla|Operador|Funcion|Constante)[A-Za-z0-9_]+)\s+(?!a\b)(.+)$"
    )
    return patron.sub(r"\1 a ex:Tabla ;\n    \2", ttl_text)


def normalizar_curies_ex_invalidos(ttl_text: str) -> str:
    resultado: list[str] = []
    i = 0
    n = len(ttl_text)
    estado = "outside"
    delimitadores = set(" \t\r\n;,.()[]{}<>\"'")

    def sanitizar_local_name(local_name: str) -> str:
        local_name = re.sub(r"[^A-Za-z0-9_]", "_", local_name)
        local_name = re.sub(r"_+", "_", local_name).strip("_")
        if not local_name:
            return local_name
        if local_name[0].isdigit():
            local_name = f"_{local_name}"
        return local_name

    while i < n:
        if estado == "outside":
            if ttl_text.startswith('"""', i):
                resultado.append('"""')
                estado = "long"
                i += 3
                continue
            if ttl_text[i] == '"' and (i == 0 or ttl_text[i - 1] != "\\"):
                resultado.append('"')
                estado = "short"
                i += 1
                continue
            if ttl_text.startswith("ex:", i):
                j = i + 3
                while j < n and ttl_text[j] not in delimitadores:
                    j += 1
                local_name = ttl_text[i + 3 : j]
                resultado.append("ex:")
                resultado.append(sanitizar_local_name(local_name) or local_name)
                i = j
                continue
            resultado.append(ttl_text[i])
            i += 1
            continue

        if estado == "long" and ttl_text.startswith('"""', i):
            resultado.append('"""')
            estado = "outside"
            i += 3
            continue

        if estado == "short" and ttl_text[i] == '"' and (i == 0 or ttl_text[i - 1] != "\\"):
            resultado.append('"')
            estado = "outside"
            i += 1
            continue

        resultado.append(ttl_text[i])
        i += 1

    return "".join(resultado)


def normalizar_vocabulario_canonico(ttl_text: str) -> str:
    ttl_normalizado = normalizar_puntuacion_problematica(ttl_text)
    reemplazos_directos = {
        "ex:textoExtractor": "ex:textoExtracto",
        "ex:textExtracto": "ex:textoExtracto",
        " rdf:type ": " a ",
        "@xsd:string": "^^xsd:string",
        "@xsd:integer": "^^xsd:integer",
        "@xsd:decimal": "^^xsd:decimal",
        "@xsd:float": "^^xsd:float",
        "@xsd:double": "^^xsd:double",
        " a rdfs:label": " rdfs:label",
        " a ex:Conector": " a ex:ComponenteElectrico",
        " a ex:Relay": " a ex:ComponenteElectrico",
        " a ex:Rel?": " a ex:ComponenteElectrico",
        " a ex:Latiguillo": " a ex:ComponenteElectrico",
        " a ex:ComponenteNeumatico": " a ex:Componente",
    }
    for origen, destino in reemplazos_directos.items():
        ttl_normalizado = ttl_normalizado.replace(origen, destino)
    ttl_normalizado = tipar_tablas_canonicas(ttl_normalizado)
    ttl_normalizado = normalizar_curies_ex_invalidos(ttl_normalizado)
    ttl_normalizado = normalizar_hex_binary_invalidos(ttl_normalizado)
    ttl_normalizado = escapar_barras_invertidas_en_literales(ttl_normalizado)
    ttl_normalizado = escapar_comillas_internas_en_literales(ttl_normalizado)
    return ttl_normalizado


def persistir_debug_chunk_fallido(
    chunk_id: int,
    *,
    error_cause: str,
    error_message: str,
    raw_response: str | None,
    normalized_ttl: str | None,
    model_name: str | None = None,
    attempted_models: tuple[str, ...] | None = None,
) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    metadata_path = DEBUG_DIR / f"chunk_{chunk_id:03d}_failure.json"
    payload = {
        "chunk_id": chunk_id,
        "prompt_version": ABOX_PROMPT_VERSION,
        "model_name": model_name or PRIMARY_MODEL,
        "model_chain": list(get_model_chain()),
        "error_cause": error_cause,
        "error_message": error_message,
    }
    if attempted_models:
        payload["attempted_models"] = list(attempted_models)
    if raw_response:
        raw_path = DEBUG_DIR / f"chunk_{chunk_id:03d}_raw_response.txt"
        raw_path.write_text(raw_response, encoding="utf-8")
        payload["raw_response_path"] = str(raw_path)
    if normalized_ttl:
        ttl_path = DEBUG_DIR / f"chunk_{chunk_id:03d}_normalized.ttl"
        ttl_path.write_text(normalized_ttl, encoding="utf-8")
        payload["normalized_ttl_path"] = str(ttl_path)
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def llamada_llm_once(mensajes: list) -> tuple[str, str]:
    attempted_models: list[str] = []
    last_error_cause = "api_error"
    last_error_message = "No fue posible completar la llamada al LLM."
    last_model_name = PRIMARY_MODEL

    for model_name in get_model_chain():
        attempted_models.append(model_name)
        last_model_name = model_name
        try:
            respuesta = await get_client().chat.complete_async(model=model_name, temperature=0.0, messages=mensajes)
            return respuesta.choices[0].message.content, model_name
        except Exception as exc:
            last_error_cause, last_error_message = classify_exception(exc)
            continue

    attempted_display = ", ".join(attempted_models) or PRIMARY_MODEL
    raise ModelFallbackExhaustedError(
        error_cause=last_error_cause,
        error_message=f"{last_error_message} | model_chain_attempted={attempted_display}",
        attempted_models=tuple(attempted_models),
        last_model_name=last_model_name,
    )


def classify_exception(exc: Exception) -> tuple[str, str]:
    message = str(exc)
    lowered = message.lower()
    if "429" in lowered or "rate limit" in lowered or "rate_limited" in lowered:
        return "rate_limit", message
    if "timeout" in lowered:
        return "timeout", message
    if any(token in lowered for token in ["connection", "network", "dns", "socket"]):
        return "network_error", message
    return "api_error", message


def resolve_retry_profile(name: str) -> RetryProfile:
    if name == "rate-limit-drain":
        return RetryProfile(
            name=name,
            max_concurrency=ABOX_RATE_LIMIT_DRAIN_MAX_CONCURRENCY,
            max_retries=ABOX_RATE_LIMIT_DRAIN_MAX_RETRIES,
            backoff_seconds=ABOX_RATE_LIMIT_DRAIN_BACKOFF_SECONDS,
            jitter_range=ABOX_RATE_LIMIT_DRAIN_JITTER_RANGE,
            request_spacing_seconds=ABOX_RATE_LIMIT_DRAIN_REQUEST_SPACING_SECONDS,
        )
    if name == "micro-batch-recovery":
        return RetryProfile(
            name=name,
            max_concurrency=ABOX_MICRO_BATCH_RECOVERY_MAX_CONCURRENCY,
            max_retries=ABOX_MICRO_BATCH_RECOVERY_MAX_RETRIES,
            backoff_seconds=ABOX_MICRO_BATCH_RECOVERY_BACKOFF_SECONDS,
            jitter_range=ABOX_MICRO_BATCH_RECOVERY_JITTER_RANGE,
            request_spacing_seconds=ABOX_MICRO_BATCH_RECOVERY_REQUEST_SPACING_SECONDS,
        )
    return RetryProfile(
        name="standard",
        max_concurrency=int(os.environ.get("ABOX_MAX_CONCURRENCY", str(ABOX_STANDARD_MAX_CONCURRENCY))),
        max_retries=ABOX_MAX_LOCAL_RETRIES,
        backoff_seconds=ABOX_RETRY_BACKOFF_SECONDS,
        jitter_range=(1.0, 1.0),
        request_spacing_seconds=0.0,
    )


def get_backoff_seconds(attempt_index: int, retry_profile: RetryProfile) -> float:
    if attempt_index < len(retry_profile.backoff_seconds):
        base_seconds = retry_profile.backoff_seconds[attempt_index]
    else:
        base_seconds = retry_profile.backoff_seconds[-1]
    jitter = random.uniform(*retry_profile.jitter_range)
    return round(base_seconds * jitter, 3)


def construir_prompt_sistema(vocabulario: str) -> str:
    return f"""
Eres un extractor estricto de instancias (A-Box) para un Grafo de Conocimiento RDF.
Prefijo OBLIGATORIO: PREFIX ex: <{BASE_URI}>
Tambien puedes usar: PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

VOCABULARIO CANONICO PERMITIDO (NO INVENTES NADA FUERA DE ESTO):
{vocabulario}

OBJETIVO:
Extrae solo individuos utiles y de alta precision a partir del fragmento del manual.
Cada sujeto debe representar una entidad concreta del dominio descrito por el texto.

REGLAS OBLIGATORIAS:
1. PROHIBIDO crear clases nuevas, propiedades nuevas o vocabulario auxiliar fuera de la T-Box canonica.
2. Si una palabra del texto no coincide exactamente con una clase permitida (por ejemplo rele, relay, conector, motor, columna luminosa, latiguillo), debes mapearla a la clase canonica mas cercana ya permitida. En este manual, conectores, reles, latiguillos y pequenos elementos de cableado deben caer normalmente en ex:ComponenteElectrico, no en clases nuevas. Nunca escribas ex:Relay, ex:Rele, ex:Conector, ex:Motor, ex:ColumnaLuminosa, ex:Documento o variantes inventadas.
3. Todo individuo debe tener exactamente el tipo canonico mas especifico que puedas justificar con el texto. No mezcles tipos incompatibles ni dupliques un tipo generico si ya usas uno especifico.
4. Cada individuo extraido debe llevar ex:textoExtracto con una cita literal o fragmento fiel del texto fuente que justifica su existencia.
4.b. Conserva el idioma original del fragmento en los literales textuales. Si el chunk esta en ingles, no traduzcas ex:textoExtracto ni rdfs:label de cita textual; si esta en espanol, mantenlos en espanol.
5. Usa ex:identificador solo para codigos, referencias, directivas, modelos o designadores textuales observables en el fragmento.
6. Usa solo propiedades canonicas. Si necesitas expresar fabricante, referencia comercial o unidad, absorbelo en rdfs:label, ex:identificador, ex:valor o ex:textoExtracto, pero NO inventes propiedades como ex:fabricadoPor, ex:referenciaFabricante, ex:unidad o similares.
7. Prefiere entidades enlazadas mediante propiedades de objeto canonicas cuando el texto describa composicion, control, mantenimiento, seguridad, documentacion, esquema o relacion funcional. Si la relacion no es segura, omite la relacion antes que inventarla.
8. Si el fragmento es una tabla, esquema, lista de materiales o bloque de conexionado, crea una entidad ancla canonica (por ejemplo ex:Esquema, ex:Tabla, ex:Sistema o ex:InterfazUsuario, segun corresponda) y conecta a ella los componentes listados usando relaciones permitidas como ex:tieneComponente, ex:compuestoPor, ex:detalladoEnEsquema, ex:documentadoEn o ex:ilustradoEn.
9. Si extraes mas de un individuo y el texto aporta una relacion clara entre ellos, debe aparecer al menos un enlace util entre esos individuos.
10. No generes comentarios, explicaciones, Markdown ni bloques vacios. Responde exclusivamente con Turtle valida.

CRITERIOS DE CALIDAD:
- Prioriza precision semantica frente a cobertura agresiva.
- Prefiere pocas entidades bien tipadas y enlazadas a muchas entidades aisladas o ambiguas.
- Conserva trazabilidad: el chunk debe seguir siendo auditable desde ex:textoExtracto.
""".strip()


async def procesar_chunk_abox(
    semaforo: asyncio.Semaphore,
    chunk_data: dict,
    vocabulario: str,
    *,
    retry_profile: RetryProfile,
    tbox_graph: Graph,
    semantic_vocabulary,
    manifest_entries: dict[str, dict],
    manifest_lock: asyncio.Lock,
    mint_registry: dict[str, str],
    mint_registry_lock: asyncio.Lock,
    tbox_hash: str,
):
    chunk_id = chunk_data["chunk_id"]
    texto_original = chunk_data["texto_fuente"]
    output_path = OUTPUT_DIR / f"chunk_{chunk_id:03d}_abox.ttl"

    prompt_sistema = construir_prompt_sistema(vocabulario)

    contexto_chunk = (
        f"Chunk ID: {chunk_id}\n"
        f"Paginas: {chunk_data.get('paginas', '')}\n"
        f"Seccion: {chunk_data.get('seccion', '')}\n"
        f"Titulo: {chunk_data.get('titulo', '')}\n"
        f"Idioma origen: {chunk_data.get('source_language', 'es')} (confidence={chunk_data.get('language_confidence', 0.0)})\n"
        f"Nivel de densidad: {chunk_data.get('density_level', '')}\n"
        f"Terminos detectados: {', '.join(chunk_data.get('terms_found', [])) or 'Ninguno'}"
    )

    mensajes = [
        {"role": "system", "content": prompt_sistema},
        {
            "role": "user",
            "content": (
                f"Contexto del fragmento:\n{contexto_chunk}\n\n"
                f"Texto fuente del manual:\n{texto_original}\n\n"
                "Extrae solo la A-Box canonica correspondiente a este fragmento."
            ),
        },
    ]

    async with semaforo:
        last_error_cause = "api_error"
        last_error_message = "Extraccion A-Box sin detalle de error."
        last_semantic_report = None
        last_raw_response: str | None = None
        last_normalized_ttl: str | None = None
        last_model_name = PRIMARY_MODEL
        attempted_models: tuple[str, ...] = tuple()

        if es_chunk_pagina_en_blanco(chunk_data) or es_chunk_no_informativo(chunk_data):
            if es_chunk_pagina_en_blanco(chunk_data):
                ttl_puro = construir_ttl_pagina_en_blanco(chunk_data)
                placeholder_error = "pagina_en_blanco_placeholder_invalid"
            else:
                ttl_puro = construir_ttl_chunk_no_informativo(chunk_data)
                placeholder_error = "chunk_no_informativo_placeholder_invalid"
            async with mint_registry_lock:
                ttl_puro, sanitization_report = sanitize_generated_ttl(
                    ttl_puro,
                    tbox_graph=tbox_graph,
                    source_chunk_text=texto_original,
                    mint_registry=mint_registry,
                )
                save_mint_registry(mint_registry, ABOX_MINTED_ENTITY_REGISTRY_PATH)
            semantic_result = validate_abox_graph(parse_ttl_graph(ttl_puro), vocabulary=semantic_vocabulary)
            last_semantic_report = semantic_result.to_manifest_summary()
            last_semantic_report["sanitization"] = sanitization_report
            if not semantic_result.ok:
                persistir_debug_chunk_fallido(
                    chunk_id,
                    error_cause="semantic_invalid",
                    error_message=summarize_semantic_result(semantic_result),
                    raw_response=ttl_puro,
                    normalized_ttl=ttl_puro,
                    model_name=last_model_name,
                )
                entry = build_manifest_entry(
                    chunk_data,
                    output_path=output_path,
                    status="error",
                    prompt_version=ABOX_PROMPT_VERSION,
                    model_name=last_model_name,
                    extraction_mode=EXTRACTION_MODE,
                    tbox_hash=tbox_hash,
                    error_cause="semantic_invalid",
                    error_message=summarize_semantic_result(semantic_result),
                    semantic_report=last_semantic_report,
                )
                async with manifest_lock:
                    manifest_entries[str(chunk_id)] = entry
                    save_manifest(MANIFEST_PATH, manifest_entries)
                return chunk_id, f"Error[semantic_invalid]: {placeholder_error}"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(ttl_puro)
            entry = build_manifest_entry(
                chunk_data,
                output_path=output_path,
                status="ok",
                prompt_version=ABOX_PROMPT_VERSION,
                model_name=last_model_name,
                extraction_mode=EXTRACTION_MODE,
                tbox_hash=tbox_hash,
                semantic_report=last_semantic_report,
            )
            async with manifest_lock:
                manifest_entries[str(chunk_id)] = entry
                save_manifest(MANIFEST_PATH, manifest_entries)
            return chunk_id, "OK"

        for attempt in range(retry_profile.max_retries):
            api_call_attempted = False
            try:
                api_call_attempted = True
                contenido, resolved_model_name = await llamada_llm_once(mensajes)
                last_model_name = resolved_model_name
                if retry_profile.request_spacing_seconds > 0:
                    await asyncio.sleep(retry_profile.request_spacing_seconds)
                last_raw_response = contenido
                ttl_puro = aislar_sintaxis_ttl(contenido)
                if not ttl_puro.strip():
                    last_error_cause = "empty_response"
                    last_error_message = "La respuesta del modelo llego vacia tras aislar el TTL."
                else:
                    ttl_puro = garantizar_prefijos_obligatorios(ttl_puro)
                    ttl_puro = normalizar_vocabulario_canonico(ttl_puro)
                    last_normalized_ttl = ttl_puro
                    ttl_ok, ttl_error = validate_ttl_text(ttl_puro)
                    if ttl_ok:
                        async with mint_registry_lock:
                            ttl_puro, sanitization_report = sanitize_generated_ttl(
                                ttl_puro,
                                tbox_graph=tbox_graph,
                                source_chunk_text=texto_original,
                                mint_registry=mint_registry,
                            )
                            save_mint_registry(mint_registry, ABOX_MINTED_ENTITY_REGISTRY_PATH)
                        semantic_result = validate_abox_graph(parse_ttl_graph(ttl_puro), vocabulary=semantic_vocabulary)
                        last_semantic_report = semantic_result.to_manifest_summary()
                        last_semantic_report["sanitization"] = sanitization_report
                        if semantic_result.ok:
                            with open(output_path, "w", encoding="utf-8") as f:
                                f.write(ttl_puro)
                            entry = build_manifest_entry(
                                chunk_data,
                                output_path=output_path,
                                status="ok",
                                prompt_version=ABOX_PROMPT_VERSION,
                                model_name=last_model_name,
                                extraction_mode=EXTRACTION_MODE,
                                tbox_hash=tbox_hash,
                                semantic_report=last_semantic_report,
                            )
                            async with manifest_lock:
                                manifest_entries[str(chunk_id)] = entry
                                save_manifest(MANIFEST_PATH, manifest_entries)
                            return chunk_id, "OK"
                        last_error_cause = "semantic_invalid"
                        last_error_message = summarize_semantic_result(semantic_result)
                    else:
                        last_error_cause = "ttl_invalid"
                        last_error_message = ttl_error or "El TTL generado no parsea correctamente."
            except ModelFallbackExhaustedError as exc:
                if api_call_attempted and retry_profile.request_spacing_seconds > 0:
                    await asyncio.sleep(retry_profile.request_spacing_seconds)
                last_error_cause = exc.error_cause
                last_error_message = exc.error_message
                attempted_models = exc.attempted_models
                last_model_name = exc.last_model_name
            except Exception as exc:
                if api_call_attempted and retry_profile.request_spacing_seconds > 0:
                    await asyncio.sleep(retry_profile.request_spacing_seconds)
                last_error_cause, last_error_message = classify_exception(exc)

            if output_path.exists() and last_error_cause in {"ttl_invalid", "empty_response", "semantic_invalid"}:
                output_path.unlink(missing_ok=True)

            if last_error_cause in ABOX_RETRYABLE_ERROR_CAUSES and attempt < retry_profile.max_retries - 1:
                await asyncio.sleep(get_backoff_seconds(attempt, retry_profile))
                continue
            if last_error_cause in {"ttl_invalid", "empty_response", "semantic_invalid"} and attempt < retry_profile.max_retries - 1:
                await asyncio.sleep(1)
                continue
            break

        persistir_debug_chunk_fallido(
            chunk_id,
            error_cause=last_error_cause,
            error_message=last_error_message,
            raw_response=last_raw_response,
            normalized_ttl=last_normalized_ttl,
            model_name=last_model_name,
            attempted_models=attempted_models,
        )

        entry = build_manifest_entry(
            chunk_data,
            output_path=output_path,
            status="error",
            prompt_version=ABOX_PROMPT_VERSION,
            model_name=last_model_name,
            extraction_mode=EXTRACTION_MODE,
            tbox_hash=tbox_hash,
            error_cause=last_error_cause,
            error_message=last_error_message,
            semantic_report=last_semantic_report,
        )
        async with manifest_lock:
            manifest_entries[str(chunk_id)] = entry
            save_manifest(MANIFEST_PATH, manifest_entries)
        return chunk_id, f"Error[{last_error_cause}]: {last_error_message}"


def load_abox_input() -> list[dict]:
    with open(ABOX_INPUT_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError("abox_input.json debe contener una lista de chunks.")
    return payload


async def orquestar_extraccion_abox(mode: str, chunk_ids: set[int] | None = None, retry_profile_name: str = DEFAULT_RETRY_PROFILE) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    retry_profile = resolve_retry_profile(retry_profile_name)
    vocabulario = compilar_vocabulario_tbox()
    tbox_graph = Graph()
    tbox_graph.parse(TBOX_PATH, format="turtle")
    semantic_vocabulary = load_semantic_vocabulary(TBOX_PATH)
    abox_input = load_abox_input()
    if chunk_ids:
        abox_input = [chunk for chunk in abox_input if int(chunk["chunk_id"]) in chunk_ids]
    manifest_entries = load_manifest(MANIFEST_PATH)
    manifest_lock = asyncio.Lock()
    mint_registry = load_mint_registry(ABOX_MINTED_ENTITY_REGISTRY_PATH)
    mint_registry_lock = asyncio.Lock()
    semaforo = asyncio.Semaphore(retry_profile.max_concurrency)
    tbox_hash = hash_file_content(TBOX_PATH)

    chunks_to_run: list[dict] = []
    reutilizados = 0
    marcados_missing = 0
    marcados_stale = 0
    reintentos_error = 0

    for chunk in abox_input:
        chunk_id = chunk["chunk_id"]
        output_path = OUTPUT_DIR / f"chunk_{chunk_id:03d}_abox.ttl"
        manifest_entry = manifest_entries.get(str(chunk_id))
        action, status = determine_chunk_action(
            chunk,
            output_path=output_path,
            manifest_entry=manifest_entry,
            mode=mode,
            prompt_version=ABOX_PROMPT_VERSION,
            model_name=PRIMARY_MODEL,
            extraction_mode=EXTRACTION_MODE,
            compatible_model_names=get_model_chain(),
            tbox_hash=tbox_hash,
        )

        if action == "reuse":
            ttl_ok, ttl_error = validate_ttl_file(output_path)
            if ttl_ok:
                semantic_result = validate_ttl_file_semantics(output_path, vocabulary=semantic_vocabulary)
                if semantic_result.ok:
                    reutilizados += 1
                    manifest_entries[str(chunk_id)] = build_manifest_entry(
                        chunk,
                        output_path=output_path,
                        status="ok",
                        prompt_version=ABOX_PROMPT_VERSION,
                        model_name=str((manifest_entry or {}).get("model_name") or PRIMARY_MODEL),
                        extraction_mode=EXTRACTION_MODE,
                        tbox_hash=tbox_hash,
                        semantic_report=semantic_result.to_manifest_summary(),
                    )
                    continue
                ttl_error = summarize_semantic_result(semantic_result)
                error_cause = "semantic_invalid"
            else:
                error_cause = "ttl_invalid"

            output_path.unlink(missing_ok=True)
            manifest_entries[str(chunk_id)] = build_manifest_entry(
                chunk,
                output_path=output_path,
                status="error",
                prompt_version=ABOX_PROMPT_VERSION,
                model_name=str((manifest_entry or {}).get("model_name") or PRIMARY_MODEL),
                extraction_mode=EXTRACTION_MODE,
                tbox_hash=tbox_hash,
                error_cause=error_cause,
                error_message=ttl_error or "El TTL previamente reutilizable no valida correctamente.",
            )
            reintentos_error += 1
            chunks_to_run.append(chunk)
            continue

        manifest_entries[str(chunk_id)] = build_manifest_entry(
            chunk,
            output_path=output_path,
            status=status,
            prompt_version=ABOX_PROMPT_VERSION,
            model_name=PRIMARY_MODEL,
            extraction_mode=EXTRACTION_MODE,
            tbox_hash=tbox_hash,
        )
        if status == "missing":
            marcados_missing += 1
        elif status == "stale":
            marcados_stale += 1
        elif status == "error":
            reintentos_error += 1

        chunks_to_run.append(chunk)

    save_manifest(MANIFEST_PATH, manifest_entries)

    alcance = f" ({len(abox_input)} bloques)"
    if chunk_ids:
        alcance = f" ({len(abox_input)} bloques filtrados: {sorted(chunk_ids)})"
    print(f"Iniciando extraccion A-Box en modo {mode}{alcance} con perfil {retry_profile.name}...")
    print(f"Cadena de modelos Mistral: {', '.join(get_model_chain())}")

    if chunks_to_run:
        try:
            get_client()
        except RuntimeError as exc:
            print(str(exc))
            print("Se guardo el manifiesto con el estado planificado, pero no se lanzaron regeneraciones.")
            return 1

    tareas = [
        procesar_chunk_abox(
            semaforo,
            chunk,
            vocabulario,
            retry_profile=retry_profile,
            tbox_graph=tbox_graph,
            semantic_vocabulary=semantic_vocabulary,
            manifest_entries=manifest_entries,
            manifest_lock=manifest_lock,
            mint_registry=mint_registry,
            mint_registry_lock=mint_registry_lock,
            tbox_hash=tbox_hash,
        )
        for chunk in chunks_to_run
    ]

    resultados = await asyncio.gather(*tareas) if tareas else []
    exitos = sum(1 for _, estado in resultados if estado == "OK")
    errores = sum(1 for _, estado in resultados if estado.startswith("Error"))

    print(
        "Extraccion completada. "
        f"Perfil: {retry_profile.name} | "
        f"Reutilizados: {reutilizados} | "
        f"Regenerados OK: {exitos} | "
        f"Marcados missing: {marcados_missing} | "
        f"Marcados stale: {marcados_stale} | "
        f"Reintentos por error: {reintentos_error} | "
        f"Errores actuales: {errores}"
    )
    return 1 if errores > 0 else 0


if __name__ == "__main__":
    args = parse_args()
    ABOX_INPUT_PATH = args.abox_input
    MANIFEST_PATH = args.manifest_path
    OUTPUT_DIR = args.output_dir
    DEBUG_DIR = args.debug_dir
    raise SystemExit(asyncio.run(orquestar_extraccion_abox(args.mode, parse_chunk_ids(args.chunk_ids), args.retry_profile)))
