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
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from openai import AsyncOpenAI
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from artifact_contracts import (
    ABOX_CHUNKS_DIR,
    ABOX_DEBUG_DIR,
    ABOX_MINTED_ENTITY_REGISTRY_PATH,
    ABOX_MAX_LOCAL_RETRIES,
    ABOX_LOCAL_HIGH_THROUGHPUT_BACKOFF_SECONDS,
    ABOX_LOCAL_HIGH_THROUGHPUT_JITTER_RANGE,
    ABOX_LOCAL_HIGH_THROUGHPUT_MAX_CONCURRENCY,
    ABOX_LOCAL_HIGH_THROUGHPUT_MAX_RETRIES,
    ABOX_LOCAL_HIGH_THROUGHPUT_REQUEST_SPACING_SECONDS,
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
    OLLAMA_BASE_URL,
    OPERATIONAL_ABOX_INPUT_PATH,
    OPERATIONAL_ABOX_MANIFEST_PATH,
    OPERATIONAL_TBOX_PATH,
    hash_file_content,
    resolve_ollama_model_chain,
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
MODEL_CHAIN = resolve_ollama_model_chain()
PRIMARY_MODEL = MODEL_CHAIN[0]
BASE_URI = "https://vocab.cfaa.eus/broaching/"
EX_IDENTIFICADOR = URIRef(BASE_URI + "identificador")
ABOX_PROMPT_VERSION = "semantic-guardrails-v5-predicate-rules"
EXTRACTION_MODE = "abox_from_text_chunk"
DEFAULT_MODE = "resume-compatible"
DEFAULT_RETRY_PROFILE = "standard"

client: AsyncOpenAI | None = None


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
        choices=["standard", "rate-limit-drain", "micro-batch-recovery", "local-high-throughput"],
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


def get_client() -> AsyncOpenAI:
    global client
    if client is None:
        client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
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


def normalize_identifier(value: str) -> str:
    return re.sub(r"[\s\-/]+", "", value or "").upper()


def detect_intra_chunk_identifier_duplicates(graph: Graph) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for subject in graph.subjects(RDF.type, None):
        if not isinstance(subject, URIRef):
            continue
        local_types = [
            str(obj).replace(BASE_URI, "")
            for obj in graph.objects(subject, RDF.type)
            if isinstance(obj, URIRef) and str(obj).startswith(BASE_URI)
        ]
        identifiers = [
            normalize_identifier(str(obj))
            for obj in graph.objects(subject, EX_IDENTIFICADOR)
            if isinstance(obj, Literal) and str(obj).strip()
        ]
        for entity_type in local_types:
            for identifier in identifiers:
                if len(identifier) >= 2:
                    groups[(entity_type, identifier)].append(str(subject))

    conflicts: list[dict[str, object]] = []
    for (entity_type, identifier), uris in groups.items():
        unique_uris = list(dict.fromkeys(uris))
        if len(unique_uris) > 1:
            conflicts.append({"class": entity_type, "identifier": identifier, "uris": unique_uris})
    return conflicts


def merge_intra_chunk_duplicates(graph: Graph, conflicts: list[dict[str, object]]) -> tuple[Graph, int]:
    mapping: dict[str, str] = {}
    for conflict in conflicts:
        uris = [str(uri) for uri in conflict.get("uris", [])]
        degrees = {
            uri: (
                sum(1 for _ in graph.predicate_objects(URIRef(uri)))
                + sum(1 for _ in graph.subject_predicates(URIRef(uri)))
            )
            for uri in uris
        }
        if not degrees:
            continue
        canonical = sorted(uris, key=lambda uri: (-degrees[uri], len(uri), uri))[0]
        for uri in uris:
            if uri != canonical:
                mapping[uri] = canonical

    if not mapping:
        return graph, 0

    merged = Graph()
    for prefix, namespace in graph.namespaces():
        merged.bind(prefix, namespace)
    skipped_self_loops = 0
    for subject, predicate, obj in graph:
        new_subject = URIRef(mapping[str(subject)]) if isinstance(subject, URIRef) and str(subject) in mapping else subject
        new_object = obj
        if predicate != RDF.type and isinstance(obj, URIRef) and str(obj) in mapping:
            new_object = URIRef(mapping[str(obj)])
        if isinstance(new_object, URIRef) and new_subject == new_object and (new_subject != subject or new_object != obj):
            skipped_self_loops += 1
            continue
        merged.add((new_subject, predicate, new_object))
    return merged, len(mapping) + skipped_self_loops


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
    intra_duplicates = detect_intra_chunk_identifier_duplicates(sanitized_graph)
    duplicate_resolution_count = 0
    if intra_duplicates:
        sanitized_graph, duplicate_resolution_count = merge_intra_chunk_duplicates(sanitized_graph, intra_duplicates)
    manifest_summary = sanitization_result.to_manifest_summary()
    manifest_summary["intra_chunk_identifier_duplicate_groups"] = len(intra_duplicates)
    manifest_summary["intra_chunk_duplicates_resolved"] = duplicate_resolution_count
    manifest_summary["sample_intra_chunk_identifier_duplicates"] = intra_duplicates[:5]
    return serialize_graph(sanitized_graph), manifest_summary


IDENTITY_RULES_SECTION = """
REGLAS DE IDENTIDAD POR CLASE:

Para ex:Parametro:
  - Si el texto contiene un codigo tecnico del parametro (ejemplos: PP177, ABSOFF, ACCJERK, G54, M3), ex:identificador debe contener ese codigo exacto.
  - Si no hay codigo tecnico, extrae el parametro solo cuando el rdfs:label sea especifico y el texto aporte evidencia clara. No extraigas parametros genericos de una sola palabra.
  - rdfs:label debe contener el nombre legible del parametro en el idioma del texto.
  - ex:valor debe contener solo valores literales explicitamente presentes, por ejemplo "400 V", "50 Hz" o "1".
  - La URI debe preferir el codigo cuando exista, por ejemplo ex:ParametroABSOFF o ex:ParametroPP177. Nunca uses frases completas ni ex:textoExtracto como base de URI.

Para ex:Parametro extraido de manuales de variables CNC (mnemonicos tipo MPG.*, MPA.*, PLC.*, SP.*, A.*):

  CRITERIO DE VALIDEZ — solo crea ex:Parametro si el chunk contiene un codigo tecnico explicito:
    - Mnemonico en notacion de punto: "MPG.VMOVAXIS1", "MPA.CAXNAME", "V.PLC.MZTOCH1"
    - Nombre de parametro maquina en MAYUSCULAS sin espacios: "INCJOGFEED", "LIMIT+", "GAPSENSORDELAY", "MODUPLIM"
    - Si el texto NO contiene ningun codigo de este tipo, no extraigas ningun Parametro aunque aparezcan palabras tecnicas.

  EXCEPCION CRITICA — tablas de sintaxis placeholder:
    - Si el chunk contiene una tabla donde el mnemonico usa "variable" como comodin (V.MPA.variable.Z, V.A.variable.S), es explicacion de notacion, NO definicion concreta. No extraigas NADA de ese chunk relacionado con Parametro, incluyendo los valores de la columna Significado (Eje Z, Cabezal S, etc.).
    - "Eje Z", "Cabezal S", "Eje o cabezal con numero logico 4" son contextos de uso, no parametros individuales.

  EXCEPCION CRITICA — nombres de funciones o secciones en mayusculas con espacios:
    - Frases como "SOFT TOOL RADIUS COMP", "HARD REAL TIME", "TOOL RADIUS COMP", "IEC 61131" son nombres de funciones o estandares, no variables CNC. No las extraigas como Parametro.
    - Un identificador de parametro real NUNCA tiene espacios: VMOVAXIS1, INCJOGFEED, CAXNAME, RETRACTTHREAD son validos; "SOFT TOOL RADIUS" no lo es.

  Formato correcto cuando hay un codigo valido:
    - ex:identificador debe contener el codigo sin prefijo "(V.)" y sin indices "[n]": "MPG.VMOVAXIS1", "MPA.CAXNAME", "INCJOGFEED".
    - rdfs:label debe ser la descripcion funcional de la variable, nunca el codigo en si.
    - URI desde el codigo en CamelCase eliminando puntos y caracteres especiales: ex:ParametroMPGVMOVAXIS1, ex:ParametroINCJOGFEED, ex:ParametroGAPSENSORDELAY.
    - Si el texto menciona "el parametro GAPSENSORDELAY ya no es funcional", el identificador es "GAPSENSORDELAY" y la URI es ex:ParametroGAPSENSORDELAY. NUNCA uses la frase descriptiva como base de URI.
    - La URI debe tener menos de 50 caracteres en el local name. Si el codigo es largo, trunca: ex:ParametroMPGVMOVAXIS1 (20 chars) es correcto; ex:ControlDelGapElParametroMaquina... (40+ chars) es incorrecto.
    - Si el chunk tiene mas de 5 variables concretas, extrae solo las 3-5 con descripcion mas completa.
    - NO crees Tabla, Pagina ni Figura para chunks de definicion de variables CNC.

Para ex:ComponenteElectrico, ex:ComponenteMecanico y ex:ComponenteHidraulico:
  - Si aparece una referencia tecnica o de fabricante (ejemplos: 3RT2024-1BB40, KA04, 19A21), ese valor debe ir en ex:identificador.
  - rdfs:label debe contener el nombre descriptivo observable.
  - No crees dos entidades distintas para el mismo numero de referencia dentro del mismo chunk.
  - Si el mismo componente aparece repetido en una tabla, crea una sola entidad y conserva la evidencia en ex:textoExtracto.

Para ex:Manual:
  - ex:identificador debe ser el codigo o titulo oficial si aparece.
  - No crees una entidad Manual generica sin identificador. Si solo hay una mencion vaga, usa ex:documentadoEn hacia una entidad existente o omite la entidad Manual.
  - "Manual de programacion", "manual de instalacion" y nombres equivalentes deben mantenerse consistentes entre chunks.

Para ex:Sistema:
  - Un sistema debe tener nombre propio, por ejemplo "Sistema Hidraulico", "Sistema PLC" o "CNC 8070".
  - No extraigas sistemas genericos sin nombre.
  - Si el sistema ya tiene nombre conocido en el contexto, reutiliza el mismo rdfs:label e identificador para favorecer la canonicalizacion.

REGLA CRITICA — URI DE CLASE NUNCA ES INDIVIDUO:
  - Los URIs de las clases del vocabulario (ex:Maquina, ex:Sistema, ex:Componente, ex:Alarma, ex:Parametro, etc.) NUNCA pueden usarse como local name de un individuo.
  - Incorrecto: ex:Maquina a ex:Maquina (el URI de la clase usado como sujeto individuo).
  - Correcto: ex:MaquinaBrochadoraA218 a ex:Maquina (URI descriptivo del individuo + clase como tipo).
  - Si el texto habla genericamente de "la maquina" sin nombre propio, crea ex:MaquinaPrincipal o ex:MaquinaBrochadora como individuo, nunca ex:Maquina.
  - Esta regla aplica a todos los nombres de clase: ex:Sistema, ex:Componente, ex:Alarma, ex:TareaMantenimiento, etc.

REGLA DE CONSISTENCIA — MISMO INDIVIDUO ENTRE CHUNKS:
  - Para la entidad principal del manual (la maquina, el CNC, el sistema principal), usa el MISMO URI en todos los chunks del mismo documento.
  - Elige el URI mas descriptivo posible (incluyendo modelo o numero de referencia si aparece en la portada) y mantenlo constante.
  - Ejemplo para este manual: ex:MaquinaBrochadoraElectromecanicaExteriorA218 debe aparecer igual en el chunk 001 y en el chunk 193.

REGLA DE CONSISTENCIA — SISTEMA CNC:
  - Cuando el texto se refiere al control numerico CNC 8070 (Fagor CNC 8070, el CNC, el control numerico), usa siempre ex:SistemaCNC como URI canonica.
  - ex:SistemaCNC a ex:Sistema ; rdfs:label "CNC 8070" .
  - NUNCA uses ex:CNC8070, ex:CNCFagor, ex:ControlNumericoCNC, ex:SistemaCNCFagor ni variantes: todos deben ser ex:SistemaCNC para facilitar la canonicalizacion entre manuales.
""".strip()


PREDICATE_RULES_SECTION = """
REGLAS DE USO DE PREDICADOS:

ex:tieneComponente / ex:compuestoPor
  - Usa solo para composicion estructural: una Maquina o Sistema apunta a su componente hijo.
  - Correcto: ex:MaquinaBrochadora ex:tieneComponente ex:ComponenteMotorPrincipal .
  - Incorrecto: usarlo entre dos TareaMantenimiento, o entre un Componente y un Parametro.

ex:requiereConsumible
  - Usa SOLO para materiales fungibles: aceites, grasas, lubricantes, filtros, retenes, juntas.
  - Valido tanto desde EntidadFisica como desde TareaMantenimiento como sujeto.
  - Correcto: ex:SistemaHidraulico ex:requiereConsumible ex:AceiteHidraulicoISO46 .
  - Correcto: ex:TareasLubricacionMensual ex:requiereConsumible ex:GrasaLitio .
  - NUNCA lo uses para componentes montados (motores, bombas, interruptores).

ex:requiereMantenimiento
  - Dominio: ex:EntidadFisica (Componente, Sistema o Maquina — el sujeto recibe el mantenimiento).
  - Rango: ex:TareaMantenimiento (el objeto es la tarea que se le aplica).
  - Correcto: ex:ComponenteBombaHidraulica ex:requiereMantenimiento ex:TareaRevisionBomba .
  - Correcto: ex:SistemaHidraulico ex:requiereMantenimiento ex:TareaRevisionHidraulica .
  - NUNCA con TareaMantenimiento como sujeto.

ex:solucionaFallo
  - Dominio ESTRICTO: ex:TareaMantenimiento (SOLO una tarea puede resolver un fallo).
  - Rango ESTRICTO: ex:DiagnosticoFallo (el fallo que queda resuelto).
  - Correcto: ex:TareaLimpiezaFiltro ex:solucionaFallo ex:FalloPresionHidraulicaBaja .
  - NUNCA con ex:Parametro como sujeto — un parametro no resuelve fallos, lo hacen las tareas.
  - NUNCA entre AccionProhibida ni entre entidades que no sean TareaMantenimiento -> DiagnosticoFallo.

ex:ejecutadoPor
  - Dominio: ex:TareaMantenimiento.
  - Rango: ex:Personal (operario, tecnico, servicio autorizado).
  - Correcto: ex:TareaRevisionAnual ex:ejecutadoPor ex:PersonalTecnicoAutorizado .
  - NUNCA desde Componente, Sistema, ModoOperacion ni Maquina como sujeto.

ex:habilitadoPor / ex:habilita
  - EXCLUSIVO para autorizacion de tareas de mantenimiento por personal cualificado.
  - Dominio ESTRICTO: ex:TareaMantenimiento. Rango ESTRICTO: ex:Personal.
  - Correcto: ex:TareaRevisionElectrica ex:habilitadoPor ex:PersonalElectricoAutorizado .
  - PROHIBIDO: usar para expresar que un parametro o funcion esta activado/gestionado por el CNC.
    Para "el parametro es controlado por el CNC" usa ex:controladoPor.
    Para "el sistema habilita la funcion" omite la relacion o usa ex:controla.

ex:controla / ex:controladoPor
  - Dominio y rango: ex:EntidadFisica (Sistema, Componente, Maquina).
  - Correcto: ex:SistemaCNC ex:controla ex:EjeX .
  - Correcto: ex:ComponentePLC ex:controladoPor ex:SistemaCNC .
  - Usar en lugar de ex:habilitadoPor cuando el CNC o PLC gestiona un parametro o funcion.

ex:activaAlarma
  - Dominio: ex:EntidadFisica (sistema o componente que genera la alarma).
  - Rango ESTRICTO: ex:Alarma (NUNCA ex:Parametro).
  - Correcto: ex:SistemaCNC ex:activaAlarma ex:AlarmaError1234 .
  - NUNCA apuntar a un Parametro; si el parametro describe la condicion de alarma, use ex:monitoreaParametro.

ex:monitoreaParametro / ex:parametroMonitoradoPor
  - Dominio: ex:EntidadFisica (Componente, Sistema, Sensor).
  - Rango: ex:Parametro.
  - Correcto: ex:SistemaRefrigeracion ex:monitoreaParametro ex:TemperaturaRefrigerante .
  - NUNCA usar en direccion inversa (Parametro -> Sistema) salvo con ex:parametroMonitoradoPor.

ex:ilustra / ex:ilustradoEn  [ATENCION — DIRECCION CRITICA]
  - ex:ilustra: el SUJETO es la figura/tabla/esquema; el OBJETO es lo que muestra.
    Correcto: ex:TablaMantenimiento ex:ilustra ex:TareaRevisionFiltros .
    Correcto: ex:EsquemaHidraulico ex:ilustra ex:SistemaHidraulico .
  - ex:ilustradoEn: el SUJETO es la entidad representada; el OBJETO es la figura que la contiene.
    Correcto: ex:ComponenteMotor ex:ilustradoEn ex:EsquemaMotorPrincipal .
    INCORRECTO: ex:EsquemaMotorPrincipal ex:ilustradoEn ex:ComponenteMotor .

ex:detalladoEnEsquema  [ATENCION — DIRECCION CRITICA]
  - El SUJETO es la entidad fisica (componente, sistema); el OBJETO es el esquema.
  - Correcto: ex:BombaHidraulica ex:detalladoEnEsquema ex:EsquemaHidraulico .
  - INCORRECTO: ex:EsquemaHidraulico ex:detalladoEnEsquema ex:BombaHidraulica .

ex:tieneFrecuencia / ex:frecuenciaAplicableA
  - USAR PREFERENTEMENTE ex:tieneFrecuencia: el SUJETO es la tarea, el OBJETO es la frecuencia.
    Correcto: ex:TareaRevisionFiltros ex:tieneFrecuencia ex:Cada1000H .
  - ex:frecuenciaAplicableA es la INVERSA: el SUJETO es la frecuencia, el OBJETO es la tarea.
    Correcto: ex:Cada1000H ex:frecuenciaAplicableA ex:TareaRevisionFiltros .
  - NUNCA usar ex:frecuenciaAplicableA con TareaMantenimiento como sujeto.

ex:mitigaRiesgo
  - Dominio: ex:AvisoSeguridad.
  - Rango: cualquier entidad a la que aplica la advertencia (AccionProhibida, Maquina, Componente).
  - Correcto: ex:AvisoElectrico ex:mitigaRiesgo ex:MaquinaPrincipal .
  - Correcto: ex:AvisoManipulacion ex:mitigaRiesgo ex:AccionModificarHardware .
""".strip()


def extract_ttl_syntax(llm_response: str) -> str:
    pattern = r"`{3}(?:turtle|ttl)?\n(.*?)`{3}"
    match = re.search(pattern, llm_response, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else llm_response.strip()


def is_blank_page_chunk(chunk_data: dict) -> bool:
    text = (chunk_data.get("texto_fuente") or "").strip().lower()
    return text in {"pagina en blanco", "página en blanco", "blank page"}


def is_non_informative_chunk(chunk_data: dict) -> bool:
    text = " ".join((chunk_data.get("texto_fuente") or "").strip().split())
    if not text:
        return True
    if is_blank_page_chunk(chunk_data):
        return False
    if re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", text):
        return False
    compact = re.sub(r"\s+", "", text)
    return len(compact) <= 12 and bool(re.fullmatch(r"[\d\W_]+", compact))


def build_blank_page_ttl(chunk_data: dict) -> str:
    pages = (chunk_data.get("paginas") or "no_page").strip("[]")
    pages_slug = re.sub(r"[^A-Za-z0-9_]+", "_", pages).strip("_") or "no_page"
    label = f"Blank page {chunk_data.get('paginas', '')}".strip()
    text_extract = chunk_data.get("texto_fuente", "BLANK PAGE")
    return (
        f'@prefix ex: <{BASE_URI}> .\n'
        '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n\n'
        f'ex:BlankPage_{pages_slug} a ex:Pagina ;\n'
        f'    rdfs:label "{label}" ;\n'
        f'    ex:textoExtracto "{text_extract}" .\n'
    )


def build_non_informative_chunk_ttl(chunk_data: dict) -> str:
    pages = (chunk_data.get("paginas") or "no_page").strip("[]")
    pages_slug = re.sub(r"[^A-Za-z0-9_]+", "_", pages).strip("_") or "no_page"
    section = " ".join((chunk_data.get("seccion") or "").split())
    label = f"Page {pages} - non-informative fragment".strip()
    if section:
        label = f"{label} ({section[:80]})"
    text_extract = f"Non-informative fragment detected on page {pages or 'unknown'}."
    return (
        f'@prefix ex: <{BASE_URI}> .\n'
        '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n\n'
        f'ex:NonInformativePage_{pages_slug} a ex:Pagina ;\n'
        f'    rdfs:label "{label}" ;\n'
        f'    ex:identificador "{pages or "no_page"}" ;\n'
        f'    ex:textoExtracto "{text_extract}" .\n'
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
        # Transliterate accented characters first: á→a, é→e, ñ→n, etc.
        nfkd = unicodedata.normalize("NFKD", local_name)
        local_name = "".join(c for c in nfkd if not unicodedata.combining(c))
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
        # Fix: resolve "a rdf:type X" before the general rdf:type → a replacement
        # to avoid producing invalid "a a X" double-keyword sequences.
        " a rdf:type ": " a ",
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
        # Qwen2.5 sometimes uses ex:tieneSistema (non-canonical) for system composition.
        "ex:tieneSistema": "ex:tieneComponente",
    }
    for origen, destino in reemplazos_directos.items():
        ttl_normalizado = ttl_normalizado.replace(origen, destino)
    # Remove rdf:type from comma-separated type lists (e.g. "a rdf:type, ex:Class" → "a ex:Class")
    ttl_normalizado = re.sub(r'\ba rdf:type,\s*', 'a ', ttl_normalizado)
    # Remove trailing rdf:type in comma lists (e.g. "a ex:Class, rdf:type" → "a ex:Class")
    ttl_normalizado = re.sub(r',\s*rdf:type(?=\s*[;.\n])', '', ttl_normalizado)
    ttl_normalizado = normalizar_bloques_con_llaves(ttl_normalizado)
    ttl_normalizado = normalizar_uri_propiedad_pegada(ttl_normalizado)
    ttl_normalizado = inferir_tipos_desde_uri(ttl_normalizado)
    # Fix trailing semicolon before ANY new subject (ex:S a ... OR ex:S ex:p ex:O)
    ttl_normalizado = re.sub(r';\s*\n(\s*\n)(ex:\w+)', r'.\n\1\2', ttl_normalizado)
    # Ensure TTL ends with "." if last meaningful token is ";" (truncated response)
    stripped = ttl_normalizado.rstrip()
    if stripped.endswith(';') or stripped.endswith(','):
        ttl_normalizado = stripped[:-1] + ' .'
    ttl_normalizado = tipar_tablas_canonicas(ttl_normalizado)
    ttl_normalizado = normalizar_curies_ex_invalidos(ttl_normalizado)
    ttl_normalizado = normalizar_hex_binary_invalidos(ttl_normalizado)
    ttl_normalizado = escapar_barras_invertidas_en_literales(ttl_normalizado)
    ttl_normalizado = escapar_comillas_internas_en_literales(ttl_normalizado)
    ttl_normalizado = destagear_literales_textoExtracto(ttl_normalizado)
    return ttl_normalizado


def normalizar_uri_propiedad_pegada(ttl_text: str) -> str:
    """Fix Qwen pattern: ex:SomeURIidentificador "value" → ex:SomeURI a ex:Class ; ex:identificador "value".

    Qwen2.5 sometimes omits the predicate and instead appends the property name
    directly to the subject URI, e.g.:
        ex:ComponenteElectricoSelectorBlancoidentificador "3SU1052-2CF60-0AA0" ;
    when it should generate:
        ex:ComponenteElectricoSelectorBlanco a ex:ComponenteElectrico ;
            ex:identificador "3SU1052-2CF60-0AA0" ;
    """
    # Match both lowercase and CamelCase variants of the known property suffixes.
    _SUFFIX_TO_PROP = [
        (r'[Ii]dentificador', 'identificador'),
        (r'[Tt]extoExtracto', 'textoExtracto'),
        (r'[Vv]alor', 'valor'),
    ]

    def _fix(m: re.Match) -> str:
        # Groups: (1) local_prefix, (2) suffix, (3) literal, (4) ending
        local_prefix = m.group(1)
        prop_name = m.group(2)
        literal = m.group(3)
        ending = (m.group(4) or '').strip() or ';'
        inferred_class = next(
            (cls for cls in _CANONICAL_CLASSES_LONGEST_FIRST if local_prefix.startswith(cls)),
            None,
        )
        if inferred_class is None:
            return m.group(0)
        prop_lower = prop_name[0].lower() + prop_name[1:]
        return f"ex:{local_prefix} a ex:{inferred_class} ;\n    ex:{prop_lower} {literal} {ending}"

    for suffix_pat, _ in _SUFFIX_TO_PROP:
        pattern = r'ex:(\w+?)(' + suffix_pat + r')\b\s+("(?:[^"\\]|\\.)*"(?:@\w+(?:-\w+)*)?)\s*([;.,]?)'
        ttl_text = re.sub(pattern, lambda m, f=_fix: f(m), ttl_text)

    return ttl_text


def normalizar_bloques_con_llaves(ttl_text: str) -> str:
    """Fix Qwen's JSON-style brace blocks: 'ex:S a { a ex:C ; p o } .' → valid Turtle.

    Qwen2.5 sometimes generates blocks like:
        ex:Subject a {
          a ex:Class ;
          ex:prop "value" ;
        } .
    which is not valid Turtle syntax. This converts them to:
        ex:Subject a ex:Class ;
            ex:prop "value" .
    """
    def _reemplazar(match: re.Match) -> str:
        sujeto = match.group(1).strip()
        interior = match.group(2).strip()
        tipo_match = re.search(r'\ba\s+(ex:\w+)\s*[;]?', interior)
        if not tipo_match:
            return match.group(0)
        tipo = tipo_match.group(1)
        resto = re.sub(r'\ba\s+ex:\w+\s*[;]?\s*', '', interior, count=1).strip()
        resto = re.sub(r'^[;]\s*', '', resto).strip()
        resto = re.sub(r'[;]\s*$', '', resto).strip()
        if resto:
            return f"{sujeto} a {tipo} ;\n    {resto} ."
        return f"{sujeto} a {tipo} ."

    return re.sub(
        r'(ex:\w+)\s+a\s+\{([^}]*)\}\s*\.',
        _reemplazar,
        ttl_text,
        flags=re.DOTALL,
    )


def destagear_literales_textoExtracto(ttl_text: str) -> str:
    """Remove language tags from ex:textoExtracto literals (e.g. "text"@es → "text").
    Qwen2.5 adds @es/@en language tags to traceability literals, which the
    semantic validator does not accept as plain-string textoExtracto values."""
    return re.sub(
        r'(ex:textoExtracto\s+"[^"]*")\s*@[a-zA-Z]{2,5}(?:-[a-zA-Z0-9]+)?',
        r'\1',
        ttl_text,
    )


_CANONICAL_CLASSES_LONGEST_FIRST: list[str] = sorted(
    [
        "ComponenteElectrico", "ComponenteMecanico", "ComponenteHidraulico",
        "TareaMantenimiento", "DiagnosticoFallo", "AvisoSeguridad", "AccionProhibida",
        "ElementoSeguridad", "ModoOperacion", "InterfazUsuario", "PiezaRecambio",
        "Maquina", "Sistema", "Componente", "Parametro", "Personal",
        "Consumible", "Manual", "Capitulo", "Directiva", "Actuador",
        "Tabla", "Esquema", "Sensor", "Alarma", "Figura", "Empresa",
        "Herramienta", "Frecuencia", "Pagina", "EPI",
    ],
    key=len,
    reverse=True,
)


def inferir_tipos_desde_uri(ttl_text: str) -> str:
    """Inject missing type triples for entities whose URI prefix matches a canonical class.

    Qwen2.5 sometimes omits 'a ex:ClassName' when the class is already encoded in the
    URI (new CamelCase style). This recovery pass restores the type declaration when
    the URI unambiguously identifies the class via its prefix.
    """
    # Collect entity URIs that already have a type declaration
    typed_uris: set[str] = set(re.findall(r'(ex:\w+)\s+a\s+ex:\w+', ttl_text))

    def _infer_class(local_name: str) -> str | None:
        for cls in _CANONICAL_CLASSES_LONGEST_FIRST:
            if local_name.startswith(cls):
                return cls
        return None

    def _inject_type(match: re.Match) -> str:
        uri = match.group(1)
        rest = match.group(2)
        if uri in typed_uris:
            return match.group(0)
        local = uri[3:]  # strip "ex:"
        inferred = _infer_class(local)
        if inferred is None:
            return match.group(0)
        typed_uris.add(uri)
        return f"{uri} a ex:{inferred} ;\n    {rest}"

    return re.sub(
        r'(ex:\w+)\s+(rdfs:label|ex:textoExtracto|ex:identificador|ex:valor)\b',
        _inject_type,
        ttl_text,
    )


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
            respuesta = await get_client().chat.completions.create(model=model_name, temperature=0.0, messages=mensajes)
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
    if name == "local-high-throughput":
        return RetryProfile(
            name=name,
            max_concurrency=ABOX_LOCAL_HIGH_THROUGHPUT_MAX_CONCURRENCY,
            max_retries=ABOX_LOCAL_HIGH_THROUGHPUT_MAX_RETRIES,
            backoff_seconds=ABOX_LOCAL_HIGH_THROUGHPUT_BACKOFF_SECONDS,
            jitter_range=ABOX_LOCAL_HIGH_THROUGHPUT_JITTER_RANGE,
            request_spacing_seconds=ABOX_LOCAL_HIGH_THROUGHPUT_REQUEST_SPACING_SECONDS,
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
3. Todo individuo debe tener exactamente el tipo canonico mas especifico que puedas justificar con el texto. El objeto de rdf:type debe ser exactamente una clase de la lista permitida, nunca un individuo, label, identificador, frase, valor o URI creada desde el texto. No mezcles tipos incompatibles ni dupliques un tipo generico si ya usas uno especifico.
4. Cada individuo extraido debe llevar ex:textoExtracto con una cita literal o fragmento fiel del texto fuente que justifica su existencia.
4.b. Conserva el idioma original del fragmento en los literales textuales. Si el chunk esta en ingles, no traduzcas ex:textoExtracto ni rdfs:label de cita textual; si esta en espanol, mantenlos en espanol.
5. Toda entidad debe tener un rdfs:label breve y especifico. Usa ex:identificador solo para codigos, referencias, directivas, modelos o designadores textuales observables en el fragmento.
6. Usa solo propiedades canonicas. Si necesitas expresar fabricante, referencia comercial o unidad, absorbelo en rdfs:label, ex:identificador, ex:valor o ex:textoExtracto, pero NO inventes propiedades como ex:fabricadoPor, ex:referenciaFabricante, ex:unidad o similares.
7. Prefiere entidades enlazadas mediante propiedades de objeto canonicas cuando el texto describa composicion, control, mantenimiento, seguridad, documentacion, esquema o relacion funcional. Si la relacion no es segura, omite la relacion antes que inventarla.
8. Si el fragmento es una tabla, esquema, lista de materiales o bloque de conexionado, crea una entidad ancla canonica (por ejemplo ex:Esquema, ex:Tabla, ex:Sistema o ex:InterfazUsuario, segun corresponda) y conecta a ella los componentes listados usando relaciones permitidas como ex:tieneComponente, ex:compuestoPor, ex:detalladoEnEsquema, ex:documentadoEn o ex:ilustradoEn.
9. Si extraes mas de un individuo y el texto aporta una relacion clara entre ellos, debe aparecer al menos un enlace util entre esos individuos.
10. Construye la URI desde el nombre descriptivo de la entidad en CamelCase, preferiblemente precedido del nombre de clase para desambiguar. Ejemplos correctos: ex:ComponenteElectricoInterruptorPrincipal, ex:TareaMantenimientoCambioDeAceite, ex:SistemaHidraulicoRefrigeracion. NUNCA uses el identificador tecnico (referencia, codigo, modelo) como base de la URI — ese valor va exclusivamente en ex:identificador. Incorrecto: ex:BROCHADORA_A218_RASHEM, ex:3RT2926_1BB00, ex:IL_EC_BK_PAC. El local name debe tener menos de 80 caracteres.
11. textoExtracto debe ser breve y no puede ser el chunk completo.
12. No extraigas entidades cuya unica evidencia sea una palabra generica.
13. No generes comentarios, explicaciones, Markdown ni bloques vacios. Responde exclusivamente con Turtle valida.

{IDENTITY_RULES_SECTION}

{PREDICATE_RULES_SECTION}

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

        if is_blank_page_chunk(chunk_data) or is_non_informative_chunk(chunk_data):
            if is_blank_page_chunk(chunk_data):
                ttl_puro = build_blank_page_ttl(chunk_data)
                placeholder_error = "pagina_en_blanco_placeholder_invalid"
            else:
                ttl_puro = build_non_informative_chunk_ttl(chunk_data)
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
                ttl_puro = extract_ttl_syntax(contenido)
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
    print(f"Cadena de modelos Ollama: {', '.join(get_model_chain())}")

    if chunks_to_run:
        get_client()

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
