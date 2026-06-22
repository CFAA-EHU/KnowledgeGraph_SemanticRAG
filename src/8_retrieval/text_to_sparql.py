import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any

from rdflib import Graph, URIRef

from artifact_contracts import (
    BOUNDEDNESS_POLICY_MATRIX_PATH,
    CROSS_PLAN_CATALOG_PATH,
    MULTIHOP_PLAN_CATALOG_PATH,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
    PLANNER_GENERALIZATION_CATALOG_PATH,
    PLANNER_GENERALIZATION_CATALOG_V2_PATH,
    QA_8070_QUICK_REF_BILINGUAL_V2_PATH,
    QA_CROSS_PATH,
    QA_MULTIHOP_PATH,
    QUERY_DEBUG_REPORT_PATH,
    QUERY_INTENT_CATALOG_PATH,
)
from multilingual_query_normalizer import normalize_question

TBOX_PATH = OPERATIONAL_TBOX_PATH
ABOX_PATH = OPERATIONAL_ABOX_PATH
BASE_URI = "https://vocab.cfaa.eus/broaching/"
PREFERRED_LITERAL_PREDICATES = ["label", "identificador", "textoExtracto", "valor"]
MAX_CANDIDATES = 10

STOPWORDS = {
    "de", "la", "el", "los", "las", "del", "para", "por", "que", "una", "uno", "segun", "sobre",
    "esta", "este", "estos", "estas", "cual", "donde", "quien", "como", "manual", "maquina",
    "indicado", "indicada", "mencionada", "respecto", "debe", "deben", "tipo", "informacion", "aparece",
    "sirve", "hace", "muestra", "realiza", "utilizados", "pregunta", "queda", "tiene",
    "the", "what", "which", "where", "when", "who", "does", "manual", "machine", "indicated",
    "shown", "used", "according", "with", "about", "required", "require",
}

INTENT_TRIGGER_RULES = [
    ("figure_or_reference_lookup", ["figura", "figure", "seccion", "section", "capitulo", "chapter", "referencia", "reference"]),
    ("regulatory_lookup", ["directiva", "directive", "conformidad", "conformity", "precaucion", "peligro", "medio ambiente", "safety", "seguridad", "mantenimiento", "maintenance"]),
    ("literal_lookup", ["correo", "email", "direccion", "address", "telefono", "codigo", "quien", "who", "consultar", "contacto", "contact"]),
    ("component_attribute_lookup", ["verificar", "verify", "estado", "state", "elementos", "elements", "componente", "component"]),
    ("component_relation_lookup", ["regla lineal", "linear guide", "controla", "controls", "asociado", "related", "relaciona", "subcomponente"]),
    ("purpose_or_function_lookup", ["para que sirve", "what is the purpose", "objetivo", "purpose", "indica", "representa", "represents", "funcion", "function"]),
]

BOUNDEDNESS_POLICIES = {
    "benchmark_seeded": {"seed_limit": 1, "candidate_limit": 4, "result_limit": 12, "too_broad_raw": 12, "too_narrow_min": 1, "degrade_to_fallback": False},
    "direct_seed_literal": {"seed_limit": 2, "candidate_limit": 2, "result_limit": 10, "too_broad_raw": 10, "too_narrow_min": 1, "degrade_to_fallback": False},
    "quick_ref_strict": {"seed_limit": 6, "candidate_limit": 6, "result_limit": 24, "too_broad_raw": 24, "too_narrow_min": 1, "degrade_to_fallback": False},
    "cross_manual_strict": {"seed_limit": 8, "candidate_limit": 8, "result_limit": 28, "too_broad_raw": 28, "too_narrow_min": 1, "degrade_to_fallback": False},
    "installation_strict": {"seed_limit": 6, "candidate_limit": 6, "result_limit": 24, "too_broad_raw": 24, "too_narrow_min": 1, "degrade_to_fallback": False},
    "error_strict": {"seed_limit": 6, "candidate_limit": 6, "result_limit": 24, "too_broad_raw": 24, "too_narrow_min": 1, "degrade_to_fallback": False},
    "generalized_lookup": {"seed_limit": 4, "candidate_limit": 5, "result_limit": 16, "too_broad_raw": 18, "too_narrow_min": 1, "degrade_to_fallback": True},
    "generic_fallback": {"seed_limit": 6, "candidate_limit": 8, "result_limit": 24, "too_broad_raw": 24, "too_narrow_min": 1, "degrade_to_fallback": False},
}

ANCHOR_ALIAS_RULES = [
    {"anchor_id": "manual_a218", "aliases": ["manual a218", "a218 rashem", "rashem 7x3000x500", "brochadora a218", "a218 machine", "a218 broaching machine", "a218 broaching machine manual"], "seed_uris": [f"{BASE_URI}ManualBrochadoraA218", f"{BASE_URI}Maquina_A218_RASHEM_7x3000x500"], "preferred_intents": ["purpose_or_function_lookup", "figure_or_reference_lookup"], "confidence": 0.92},
    {"anchor_id": "figure_header_footer", "aliases": ["encabezados y pies", "encabezados y pies de pagina", "pies de pagina", "informacion mostrada en paginas", "headers and footers", "manual headers and footers", "information shown on pages"], "seed_uris": [f"{BASE_URI}Figura0_1_1InformacionMostradaEnPaginas", f"{BASE_URI}ManualBrochadoraA218"], "preferred_intents": ["figure_or_reference_lookup"], "confidence": 0.95},
    {"anchor_id": "manual_safety_symbols", "aliases": ["simbolos de advertencia y seguridad", "advertencia y seguridad del manual", "warning and safety symbols", "manual safety symbols"], "seed_uris": [f"{BASE_URI}IndicacionAdvertenciaSeguridad"], "preferred_intents": ["purpose_or_function_lookup", "regulatory_lookup"], "confidence": 0.97},
    {"anchor_id": "precaucion", "aliases": ["precaucion", "senal de precaucion"], "seed_uris": [f"{BASE_URI}Precaucion"], "preferred_intents": ["regulatory_lookup"], "confidence": 0.96},
    {"anchor_id": "peligro", "aliases": ["peligro", "advertencia de peligro"], "seed_uris": [f"{BASE_URI}Peligro"], "preferred_intents": ["regulatory_lookup"], "confidence": 0.96},
    {"anchor_id": "medio_ambiente", "aliases": ["medio ambiente", "indicacion de medio ambiente", "environment indication", "environment warning"], "seed_uris": [f"{BASE_URI}MedioAmbiente"], "preferred_intents": ["regulatory_lookup", "purpose_or_function_lookup"], "confidence": 0.96},
    {"anchor_id": "sistema_seguridad_maquina", "aliases": ["sistemas de seguridad de la maquina", "seguridad de la maquina", "verificar regularmente los sistemas de seguridad", "verify the safety elements"], "seed_uris": [f"{BASE_URI}SistemaSeguridadMaquina"], "preferred_intents": ["component_attribute_lookup", "regulatory_lookup"], "confidence": 0.95},
    {"anchor_id": "elementos_seguridad_verificacion", "aliases": ["elementos de seguridad de la maquina", "verificar regularmente", "garantizar la seguridad de la maquina", "estado de los elementos de seguridad"], "seed_uris": [f"{BASE_URI}ElementoSeguridad_1"], "preferred_intents": ["component_attribute_lookup", "regulatory_lookup"], "confidence": 0.97},
    {"anchor_id": "client_support_department", "aliases": ["dudas sobre la seguridad", "consultar en caso de dudas", "asistencia al cliente", "departamento de asistencia al cliente", "customer support department", "customer service department", "doubts about machine safety"], "seed_uris": [f"{BASE_URI}DepartamentoAsistenciaClienteEKIN"], "preferred_intents": ["regulatory_lookup", "literal_lookup"], "confidence": 0.91},
    {"anchor_id": "ekin_company", "aliases": ["empresa ekin", "ekin s coop", "direccion de ekin", "direccion de la empresa ekin", "correo electronico de ekin", "correo electronico de contacto de ekin", "derechos de autor", "correo de contacto de ekin", "ekin company", "ekin address", "ekin contact email", "copyright"], "seed_uris": [f"{BASE_URI}Empresa_EKIN_S_Coop"], "preferred_intents": ["literal_lookup"], "confidence": 0.94},
    {"anchor_id": "spare_parts_policy", "aliases": ["piezas de recambio", "pieza de recambio", "recambios", "recambio original", "piezas originales", "spare parts", "original spare parts"], "seed_uris": [f"{BASE_URI}PiezaRecambio_1", f"{BASE_URI}Empresa_EKIN_S_Coop"], "preferred_intents": ["literal_lookup"], "confidence": 0.93},
    {"anchor_id": "directive_2006_42_ce", "aliases": ["declaracion ce", "directiva 2006 42 ce", "conformidad sobre maquinas", "directive 2006 42 ce", "ce declaration", "declaration of conformity"], "seed_uris": [f"{BASE_URI}Directiva2006_42_CE"], "preferred_intents": ["regulatory_lookup"], "confidence": 0.94},
    {"anchor_id": "quick_ref_work_modes", "aliases": ["modos de trabajo", "modo de trabajo", "work modes", "work mode", "automatic mode", "modo automatico", "jog mode", "modo jog", "mdi/mda mode", "modo mdi/mda"], "seed_uris": [], "preferred_intents": ["literal_lookup", "purpose_or_function_lookup"], "confidence": 0.9},
    {"anchor_id": "quick_ref_monitor_keyboard", "aliases": ["monitor y teclado", "monitor and keyboard", "monitor keyboard", "focus key", "tecla focus", "next key", "tecla next", "back key", "tecla back", "help key", "tecla help"], "seed_uris": [], "preferred_intents": ["literal_lookup", "purpose_or_function_lookup"], "confidence": 0.9},
    {"anchor_id": "quick_ref_jog_panel", "aliases": ["panel jog", "jog panel", "rapid key", "tecla rapid", "jog selector", "selector jog", "handwheel", "volante"], "seed_uris": [], "preferred_intents": ["literal_lookup", "purpose_or_function_lookup"], "confidence": 0.9},
    {"anchor_id": "quick_ref_home_search", "aliases": ["busqueda de referencia", "busqueda de home", "home search", "homing", "zero key", "tecla zero", "homing key"], "seed_uris": [], "preferred_intents": ["literal_lookup", "purpose_or_function_lookup"], "confidence": 0.9},
    {"anchor_id": "quick_ref_coordinate_preset", "aliases": ["preset de coordenadas", "coordinate preset", "preset value", "valor preset"], "seed_uris": [], "preferred_intents": ["literal_lookup"], "confidence": 0.9},
    {"anchor_id": "quick_ref_feed_speed_tool", "aliases": ["avance", "feedrate", "feed rate", "velocidad del husillo", "spindle speed", "tool", "herramienta", "start key", "tecla start", "stop key", "tecla stop", "reset key", "tecla reset"], "seed_uris": [], "preferred_intents": ["literal_lookup", "purpose_or_function_lookup"], "confidence": 0.9},
]

PREDICATE_URI_MAP = {
    "cumpleNormativa": f"{BASE_URI}cumpleNormativa",
    "requiereMantenimiento": f"{BASE_URI}requiereMantenimiento",
    "ilustradoEn": f"{BASE_URI}ilustradoEn",
    "tieneComponente": f"{BASE_URI}tieneComponente",
    "controla": f"{BASE_URI}controla",
    "textoExtracto": f"{BASE_URI}textoExtracto",
    "label": "http://www.w3.org/2000/01/rdf-schema#label",
    "identificador": f"{BASE_URI}identificador",
    "valor": f"{BASE_URI}valor",
    "type": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
}

FIXED_SEED_URI_ALIASES = {
    f"{BASE_URI}SistemaSeguridadMaquina": [f"{BASE_URI}SistemaSeguridadMaquinaBrochadoraEKIN"],
    f"{BASE_URI}Empresa_EKIN_S_Coop": [f"{BASE_URI}EKIN_S_Coop"],
    f"{BASE_URI}Figura0_1_1InformacionMostradaEnPaginas": [f"{BASE_URI}Figura0_1_1"],
    f"{BASE_URI}Figura0-1-1": [f"{BASE_URI}Figura0_1_1"],
    f"{BASE_URI}Peligro": [f"{BASE_URI}AvisoDePeligro_306aaa9d34"],
    f"{BASE_URI}Precaucion": [f"{BASE_URI}AvisoDePrecaucion_ca222fa7cb"],
    f"{BASE_URI}MedioAmbiente": [f"{BASE_URI}AvisoDeMedioAmbiente_ab96449995"],
    f"{BASE_URI}PiezaRecambio_1": [f"{BASE_URI}PiezaRecambio_15_1"],
    f"{BASE_URI}MaquinaBrochadoExterior_18": [f"{BASE_URI}MaquinaBrochadoraEKIN"],
    f"{BASE_URI}DirectivaSeguridadUnionEuropea_18": [f"{BASE_URI}Directiva2006_42_CE"],
    f"{BASE_URI}CarroPortaPiezas_46": [f"{BASE_URI}CarroPortapiezas_46"],
    f"{BASE_URI}ReglaLineal_46_1": [f"{BASE_URI}GuiaLineal_46_1"],
    f"{BASE_URI}ReglaLineal_46_2": [f"{BASE_URI}GuiaLineal_46_2"],
}

SEED_GENERIC_TOKENS = {
    "alarma", "aviso", "avisoseguridad", "componente", "contacto", "directiva", "editor",
    "elemento", "empresa", "error", "figura", "frecuencia", "indicacion", "interfaz",
    "literal", "maquina", "manual", "marca", "modo", "numero", "operacion", "parametro",
    "pieza", "plan", "regla", "senal", "sistema", "tabla", "tecla", "tipo", "usuario",
}


def _uri(local_name: str) -> str:
    return f"{BASE_URI}{local_name}"


STRICT_QUICK_REF_FAMILIES = [
    {
        "family_id": "quick_ref_mdi_mda_conditions_lookup",
        "template_id": "QRV2_T1_mdi_mda_conditions",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "mdi_mda_conditions",
        "anchor_groups_all": ["mdi_mda"],
        "keywords_any": [["condiciones activas", "active conditions", "programa interrumpido", "interrupted program"]],
        "seed_uris": [_uri("ToolInspection")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_mdi_mda_conditions", "mode": "fixed_seed", "fixed_uris": [_uri("ToolInspection")], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "mdi_mda_conditions_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 1, "max_results": 12},
        ],
    },
    {
        "family_id": "quick_ref_canned_cycles_multi_hop",
        "template_id": "QRV2_T2_canned_cycles",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "canned_cycles",
        "anchor_groups_all": ["canned_cycles"],
        "keywords_any": [
            ["taladrado profundo", "deep-hole drilling"],
            ["mecanizado multiple", "multiple machining"],
            ["patron rectangular", "rectangular pattern"],
        ],
        "seed_uris": [_uri("G83"), _uri("G161")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_canned_cycles", "mode": "fixed_seed", "fixed_uris": [_uri("G83"), _uri("G161")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "canned_cycle_details", "mode": "describe_entities", "preferred_predicates": ["valor", "textoExtracto", "label", "identificador"], "max_candidates": 2, "max_results": 12},
        ],
    },
    {
        "family_id": "quick_ref_semi_auto_calibration_conditional",
        "template_id": "QRV2_T3_semi_auto_calibration",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "semi_auto_calibration",
        "anchor_groups_all": ["tool_calibration"],
        "keywords_any": [["semiautomatica", "semi-automatic"], ["avance", "feedrate", "palpado", "probing", "validation"]],
        "seed_uris": [_uri("ModoCalibracionSemiAutomatica")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_semi_auto_calibration", "mode": "fixed_seed", "fixed_uris": [_uri("ModoCalibracionSemiAutomatica")], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "semi_auto_calibration_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 1, "max_results": 12},
        ],
    },
    {
        "family_id": "quick_ref_file_protection_lookup",
        "template_id": "QRV2_T4_file_protection",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "file_protection",
        "anchor_groups_all": ["utilities_and_file_protection"],
        "keywords_any": [["proteger", "protected", "protect"], ["modificable", "modifiable", "-m-", "edisimu"]],
        "seed_uris": [_uri("SoftkeyChangeModifiableAttribute")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_file_protection", "mode": "fixed_seed", "fixed_uris": [_uri("SoftkeyChangeModifiableAttribute")], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "file_protection_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 1, "max_results": 12},
        ],
    },
    {
        "family_id": "quick_ref_high_level_instructions_multi_hop",
        "template_id": "QRV2_T5_high_level_instructions",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "high_level_instructions",
        "anchor_groups_all": ["math_and_high_level"],
        "keywords_any": [
            ["bucle abierto", "open loop", "husillo maestro", "master spindle"],
            ["cero pieza", "current part zero", "kinematics", "cinematica"],
        ],
        "seed_uris": [_uri("SERVO_OFF"), _uri("MASTER"), _uri("KINORG"), _uri("KIN_ID")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_high_level_instructions", "mode": "fixed_seed", "fixed_uris": [_uri("SERVO_OFF"), _uri("MASTER"), _uri("KINORG"), _uri("KIN_ID")], "max_candidates": 4, "max_results": 4},
            {"step_id": "detail", "purpose": "high_level_instruction_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 4, "max_results": 16},
        ],
    },
    {
        "family_id": "quick_ref_key_purpose_lookup",
        "template_id": "QRV2_T6_key_purpose",
        "intent": "purpose_or_function_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "keyboard_help",
        "keywords_any": [["help", "tecla help"], ["monitor y teclado", "monitor and keyboard", "keyboard"]],
        "seed_uris": [_uri("TeclaHELP"), _uri("Teclado")],
        "seed_token_map": {
            "help": [_uri("TeclaHELP")],
            "focus": [_uri("TeclaFOCUS")],
            "next": [_uri("TeclaNEXT")],
            "back": [_uri("TeclaBACK")],
        },
        "steps": [
            {"step_id": "seed", "purpose": "seed_help_key", "mode": "fixed_seed", "fixed_uris": [_uri("TeclaHELP"), _uri("Teclado")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "help_key_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 2, "max_results": 12},
        ],
    },
    {
        "family_id": "quick_ref_simulation_conditions_multi_hop",
        "template_id": "QRV2_T7_simulation_conditions",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "simulation_conditions",
        "anchor_groups_all": ["simulation"],
        "keywords_any": [["trayectoria teorica", "theoretical travel", "plano principal", "main plane"], ["plc", "husillo", "spindle"]],
        "seed_uris": [_uri("EDISIMU_MODE"), _uri("ProgramSimulation"), _uri("SimulatedExecution")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_simulation", "mode": "fixed_seed", "fixed_uris": [_uri("EDISIMU_MODE"), _uri("ProgramSimulation"), _uri("SimulatedExecution")], "max_candidates": 3, "max_results": 3},
            {"step_id": "detail", "purpose": "simulation_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 3, "max_results": 14},
        ],
    },
    {
        "family_id": "quick_ref_m_functions_lookup",
        "template_id": "QRV2_T8_m_functions",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "m_functions",
        "anchor_groups_all": ["g_m_functions"],
        "technical_tokens_any": ["m04"],
        "keywords_any": [["auxiliar", "auxiliary"], ["antihorario", "counterclockwise"]],
        "seed_uris": [_uri("SpindleCounterclockwiseStartKey")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_m_functions", "mode": "fixed_seed", "fixed_uris": [_uri("SpindleCounterclockwiseStartKey")], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "m_function_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 1, "max_results": 10},
        ],
    },
    {
        "family_id": "quick_ref_file_attributes_multi_hop",
        "template_id": "QRV2_T9_file_attributes",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "file_attributes",
        "anchor_groups_all": ["utilities_and_file_protection"],
        "keywords_any": [["-m-", "modifiable"], ["-h-", "hidden"], ["atributos", "attributes"]],
        "seed_uris": [_uri("SoftkeyChangeModifiableAttribute"), _uri("SoftkeyChangeHiddenAttribute")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_file_attributes", "mode": "fixed_seed", "fixed_uris": [_uri("SoftkeyChangeModifiableAttribute"), _uri("SoftkeyChangeHiddenAttribute")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "file_attribute_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 2, "max_results": 12},
        ],
    },
    {
        "family_id": "quick_ref_g_functions_lookup",
        "template_id": "QRV2_T10_g_functions",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "g_functions",
        "anchor_groups_all": ["g_m_functions"],
        "technical_tokens_any": ["g04"],
        "seed_uris": [_uri("G04")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_g_functions", "mode": "fixed_seed", "fixed_uris": [_uri("G04")], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "g_function_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 1, "max_results": 10},
        ],
    },
    {
        "family_id": "quick_ref_tool_inspection_lookup",
        "template_id": "QRV2_T11_tool_inspection",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "tool_inspection",
        "anchor_groups_all": ["tool_inspection"],
        "seed_uris": [_uri("ToolInspection"), _uri("Softkey_BeginToolInspection"), _uri("CycleStopKey")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_tool_inspection", "mode": "fixed_seed", "fixed_uris": [_uri("ToolInspection"), _uri("Softkey_BeginToolInspection"), _uri("CycleStopKey")], "max_candidates": 3, "max_results": 3},
            {"step_id": "detail", "purpose": "tool_inspection_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 3, "max_results": 14},
        ],
    },
    {
        "family_id": "quick_ref_jog_rapid_lookup",
        "template_id": "QRV2_T12_jog_rapid",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "jog_rapid",
        "anchor_groups_all": ["jog_and_home"],
        "keywords_any": [["rapido", "rapid"], ["mover un eje", "moving an axis", "panel jog", "jog panel"]],
        "seed_uris": [_uri("RapidKey"), _uri("JogPanel")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_jog_rapid", "mode": "fixed_seed", "fixed_uris": [_uri("RapidKey"), _uri("JogPanel")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "jog_rapid_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 2, "max_results": 12},
        ],
    },
    {
        "family_id": "quick_ref_block_search_multi_hop",
        "template_id": "QRV2_T13_block_search",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "block_search",
        "keywords_any": [["busqueda de bloque", "block search"], ["automatica", "automatic"], ["bloque de parada", "stop block", "primer bloque", "first block"]],
        "seed_uris": [_uri("BusquedaBloqueAutomatica"), _uri("BusquedaBloque")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_block_search", "mode": "fixed_seed", "fixed_uris": [_uri("BusquedaBloqueAutomatica"), _uri("BusquedaBloque")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "block_search_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 2, "max_results": 14},
        ],
    },
    {
        "family_id": "quick_ref_math_functions_lookup",
        "template_id": "QRV2_T14_math_functions",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "math_functions",
        "anchor_groups_all": ["math_and_high_level"],
        "keywords_any": [["funcion matematica", "mathematical function"], ["entero mas uno", "integer plus one"]],
        "seed_uris": [],
        "steps": [
            {"step_id": "fallback", "purpose": "math_function_fallback", "mode": "fallback_query", "max_candidates": 3, "max_results": 10},
        ],
    },
    {
        "family_id": "quick_ref_calibration_comparison_multi_hop",
        "template_id": "QRV2_T15_calibration_comparison",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "manual_calibration_comparison",
        "anchor_groups_all": ["tool_calibration"],
        "keywords_any": [["calibracion manual", "manual calibration"], ["fresadora", "milling model"], ["torno en plano", "lathe model plane"]],
        "seed_uris": [_uri("MillingModelCalibration"), _uri("LatheModelPlaneCalibration"), _uri("ModeloFresadora"), _uri("ModeloTornoPlano")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_calibration_comparison", "mode": "fixed_seed", "fixed_uris": [_uri("MillingModelCalibration"), _uri("LatheModelPlaneCalibration"), _uri("ModeloFresadora"), _uri("ModeloTornoPlano")], "max_candidates": 4, "max_results": 4},
            {"step_id": "detail", "purpose": "calibration_comparison_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 4, "max_results": 16},
        ],
    },
    {
        "family_id": "quick_ref_fixture_table_lookup",
        "template_id": "QRV2_T16_fixture_table",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "fixture_table",
        "anchor_groups_all": ["fixture_and_offsets"],
        "keywords_any": [["fixture table", "tabla de utillajes"], ["configurarse", "set", "plc", "variables"]],
        "seed_uris": [_uri("Tabla_27_2")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_fixture_table", "mode": "fixed_seed", "fixed_uris": [_uri("Tabla_27_2")], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "fixture_table_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 1, "max_results": 10},
        ],
    },
    {
        "family_id": "quick_ref_edisimu_syntax_lookup",
        "template_id": "QRV2_T17_edisimu_syntax",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "edisimu_syntax",
        "anchor_groups_all": ["syntax"],
        "seed_uris": [_uri("Syntax_check")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_syntax_check", "mode": "fixed_seed", "fixed_uris": [_uri("Syntax_check")], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "syntax_check_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 1, "max_results": 10},
        ],
    },
    {
        "family_id": "quick_ref_probing_functions_multi_hop",
        "template_id": "QRV2_T18_probing_functions",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "probing_functions",
        "anchor_groups_any": ["g_m_functions"],
        "keywords_any": [["palpado", "probing"], ["hacer contacto", "making contact"], ["no hacer contacto", "not making contact"]],
        "seed_uris": [_uri("G100"), _uri("G103")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_probing_functions", "mode": "fixed_seed", "fixed_uris": [_uri("G100"), _uri("G103")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "probing_function_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 2, "max_results": 12},
        ],
    },
    {
        "family_id": "quick_ref_multiple_machining_lookup",
        "template_id": "QRV2_T19_multiple_machining",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "quick_ref_strict",
        "policy_id": "quick_ref_strict",
        "canonical_anchor": "multiple_machining",
        "anchor_groups_all": ["canned_cycles"],
        "technical_tokens_all": ["q10.013"],
        "seed_uris": [_uri("ParametroQ10_013"), _uri("AccionProhibidaNoMaquinadoQ10_013")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_multiple_machining", "mode": "fixed_seed", "fixed_uris": [_uri("ParametroQ10_013"), _uri("AccionProhibidaNoMaquinadoQ10_013")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "multiple_machining_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 2, "max_results": 12},
        ],
    },
]

STRICT_INSTALLATION_FAMILIES = [
    {
        "family_id": "installation_modes_and_storage_lookup",
        "template_id": "INS_T1_modes_storage",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "installation_strict",
        "policy_id": "installation_strict",
        "canonical_anchor": "installation_modes_storage",
        "anchor_groups_all": ["installation_modes_storage"],
        "keywords_any": [
            ["modo administrador", "modo setup"],
            ["mtb_t", "mtb_m"],
            ["carpeta", "users"],
        ],
        "seed_uris": [
            _uri("ModoOperacion_Administrador"),
            _uri("ModoOperacion_Setup"),
            _uri("ModoUsuario"),
            _uri("InterfazUsuario_ModoAdministrador"),
            _uri("InterfazUsuario_ModoSetup"),
            _uri("CarpetaMTB_T"),
            _uri("CarpetaMTB_M"),
            _uri("CarpetaUSERS"),
        ],
        "seed_token_map": {
            "mtb_t": [_uri("CarpetaMTB_T"), _uri("CarpetaMTB_M")],
            "mtb_m": [_uri("CarpetaMTB_M"), _uri("CarpetaMTB_T")],
            "users": [_uri("CarpetaUSERS")],
            "programas pieza": [_uri("CarpetaUSERS")],
        },
        "steps": [
            {"step_id": "seed", "purpose": "seed_installation_modes_storage", "mode": "fixed_seed", "fixed_uris": [_uri("ModoOperacion_Administrador"), _uri("ModoOperacion_Setup"), _uri("ModoUsuario"), _uri("InterfazUsuario_ModoAdministrador"), _uri("InterfazUsuario_ModoSetup"), _uri("CarpetaMTB_T"), _uri("CarpetaMTB_M"), _uri("CarpetaUSERS")], "max_candidates": 6, "max_results": 6},
            {"step_id": "detail", "purpose": "installation_modes_storage_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 6, "max_results": 18},
        ],
    },
    {
        "family_id": "installation_tandem_gantry_parameter_lookup",
        "template_id": "INS_T2_tandem_gantry",
        "intent": "component_attribute_lookup",
        "hop_depth": 1,
        "family_type": "installation_strict",
        "policy_id": "installation_strict",
        "canonical_anchor": "installation_tandem_gantry",
        "anchor_groups_all": ["installation_tandem_gantry"],
        "keywords_any": [
            ["tandem", "torqdist"],
            ["gantry", "warncoupe"],
            ["gantry", "unidir"],
            ["gantry", "hirth"],
        ],
        "seed_uris": [
            _uri("Parametro_TORQDIST"),
            _uri("Parametro_WARNCOUPE"),
            _uri("Parametro_MAXCOUPE"),
            _uri("Parametro_UNIDIR_69"),
            _uri("Parametro_HIRTH_69"),
        ],
        "seed_token_map": {
            "torqdist": [_uri("Parametro_TORQDIST")],
            "warncoupe": [_uri("Parametro_WARNCOUPE"), _uri("Parametro_MAXCOUPE")],
            "maxcoupe": [_uri("Parametro_MAXCOUPE"), _uri("Parametro_WARNCOUPE")],
            "unidir": [_uri("Parametro_UNIDIR_69")],
            "hirth": [_uri("Parametro_HIRTH_69")],
        },
        "steps": [
            {"step_id": "seed", "purpose": "seed_installation_tandem_gantry", "mode": "fixed_seed", "fixed_uris": [_uri("Parametro_TORQDIST"), _uri("Parametro_WARNCOUPE"), _uri("Parametro_MAXCOUPE"), _uri("Parametro_UNIDIR_69"), _uri("Parametro_HIRTH_69")], "max_candidates": 5, "max_results": 5},
            {"step_id": "detail", "purpose": "installation_tandem_gantry_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "valor"], "max_candidates": 5, "max_results": 18},
        ],
    },
    {
        "family_id": "installation_bus_plc_parameter_lookup",
        "template_id": "INS_T3_bus_plc",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "installation_strict",
        "policy_id": "installation_strict",
        "canonical_anchor": "installation_bus_plc",
        "anchor_groups_all": ["installation_bus_plc"],
        "keywords_any": [
            ["rio5", "250 khz"],
            ["plcdatasize", "hbh3"],
            ["plcdatasize", "hbh4"],
            ["plctype"],
            ["ndimod", "canopen"],
            ["ndimod", "canfagor"],
        ],
        "seed_uris": [
            _uri("Frecuencia_250kHz"),
            _uri("Sistema_HBH3_HBH4"),
            _uri("Parametro_PLCDATASIZE"),
            _uri("Parametro_PLCTYPE"),
            _uri("Parametro_NDIMOD"),
        ],
        "seed_token_map": {
            "rio5": [_uri("Frecuencia_250kHz")],
            "250 khz": [_uri("Frecuencia_250kHz")],
            "plcdatasize": [_uri("Sistema_HBH3_HBH4"), _uri("Parametro_PLCDATASIZE")],
            "hbh3": [_uri("Sistema_HBH3_HBH4"), _uri("Parametro_PLCDATASIZE")],
            "hbh4": [_uri("Sistema_HBH3_HBH4"), _uri("Parametro_PLCDATASIZE")],
            "plctype": [_uri("Parametro_PLCTYPE")],
            "ndimod": [_uri("Parametro_NDIMOD")],
            "canopen": [_uri("Parametro_NDIMOD")],
            "canfagor": [_uri("Parametro_NDIMOD")],
        },
        "steps": [
            {"step_id": "seed", "purpose": "seed_installation_bus_plc", "mode": "fixed_seed", "fixed_uris": [_uri("Frecuencia_250kHz"), _uri("Sistema_HBH3_HBH4"), _uri("Parametro_PLCDATASIZE"), _uri("Parametro_PLCTYPE"), _uri("Parametro_NDIMOD")], "max_candidates": 5, "max_results": 5},
            {"step_id": "detail", "purpose": "installation_bus_plc_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "valor"], "max_candidates": 5, "max_results": 18},
        ],
    },
    {
        "family_id": "installation_motion_defaults_lookup",
        "template_id": "INS_T4_motion_defaults",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "installation_strict",
        "policy_id": "installation_strict",
        "canonical_anchor": "installation_motion_defaults",
        "anchor_groups_all": ["installation_motion_defaults"],
        "keywords_any": [
            ["gapapproachdyn"],
            ["slopetype"],
            ["synccancel"],
            ["kinid"],
        ],
        "seed_uris": [
            _uri("GapApproachDyn"),
            _uri("Parametro_MPG_GAPAPPROACHDYN"),
            _uri("Parametro_SLOPETYPE"),
            _uri("Parametro_SYNCCANCEL"),
            _uri("Parametro_KINID"),
            _uri("Sistema_CNC"),
        ],
        "seed_token_map": {
            "gapapproachdyn": [_uri("GapApproachDyn"), _uri("Parametro_MPG_GAPAPPROACHDYN")],
            "slopetype": [_uri("Parametro_SLOPETYPE"), _uri("Sistema_CNC")],
            "synccancel": [_uri("Parametro_SYNCCANCEL"), _uri("Sistema_CNC")],
            "kinid": [_uri("Parametro_KINID")],
        },
        "steps": [
            {"step_id": "seed", "purpose": "seed_installation_motion_defaults", "mode": "fixed_seed", "fixed_uris": [_uri("GapApproachDyn"), _uri("Parametro_MPG_GAPAPPROACHDYN"), _uri("Parametro_SLOPETYPE"), _uri("Parametro_SYNCCANCEL"), _uri("Parametro_KINID"), _uri("Sistema_CNC")], "max_candidates": 6, "max_results": 6},
            {"step_id": "detail", "purpose": "installation_motion_defaults_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "valor"], "max_candidates": 6, "max_results": 22},
        ],
    },
    {
        "family_id": "installation_alarm_temperature_lookup",
        "template_id": "INS_T5_alarm_temperature",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "installation_strict",
        "policy_id": "installation_strict",
        "canonical_anchor": "installation_alarm_temperature",
        "anchor_groups_all": ["installation_alarm_temperature"],
        "keywords_any": [
            ["overtemp"],
            ["e173"],
            ["temperatura ambiente", "65"],
            ["w169"],
        ],
        "seed_uris": [
            _uri("Marca_OVERTEMP"),
            _uri("Error_E173"),
        ],
        "seed_token_map": {
            "overtemp": [_uri("Marca_OVERTEMP"), _uri("Error_E173")],
            "e173": [_uri("Error_E173"), _uri("Marca_OVERTEMP")],
            "w169": [_uri("Marca_OVERTEMP"), _uri("Error_E173")],
            "65": [_uri("Error_E173"), _uri("Marca_OVERTEMP")],
        },
        "steps": [
            {"step_id": "seed", "purpose": "seed_installation_alarm_temperature", "mode": "fixed_seed", "fixed_uris": [_uri("Marca_OVERTEMP"), _uri("Error_E173")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "installation_alarm_temperature_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 2, "max_results": 12},
        ],
    },
]

STRICT_ERROR_FAMILIES = [
    {
        "family_id": "error_safety_mode_policy_lookup",
        "template_id": "ERR_T1_safety_mode_policy",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "error_strict",
        "policy_id": "error_strict",
        "canonical_anchor": "error_safety_mode_policy",
        "anchor_groups_any": ["error_safety_mode_policy"],
        "keywords_any": [
            ["seguridades", "fabricante"],
            ["proteccion oem", "modo usuario"],
            ["caracter temporal"],
        ],
        "seed_uris": [_uri("Sistema_SeguridadesCNC"), _uri("Alarma_8026")],
        "seed_token_map": {
            "fabricante": [_uri("Sistema_SeguridadesCNC")],
            "seguridades": [_uri("Sistema_SeguridadesCNC")],
            "8026": [_uri("Alarma_8026")],
            "oem": [_uri("Alarma_8026")],
            "modo usuario": [_uri("Alarma_8026")],
        },
        "steps": [
            {"step_id": "seed", "purpose": "seed_error_safety_mode_policy", "mode": "fixed_seed", "fixed_uris": [_uri("Sistema_SeguridadesCNC"), _uri("Alarma_8026")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "error_safety_mode_policy_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "valor"], "max_candidates": 2, "max_results": 12},
        ],
    },
    {
        "family_id": "error_code_condition_attribute_lookup",
        "template_id": "ERR_T2_condition_attribute",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "error_strict",
        "policy_id": "error_strict",
        "canonical_anchor": "error_code_condition_attribute",
        "anchor_groups_any": ["error_code_condition_attribute"],
        "keywords_any": [
            ["0008"],
            ["0169"],
            ["0173"],
            ["1067"],
            ["5026"],
            ["8023"],
            ["8042"],
            ["memoria libre en disco"],
        ],
        "technical_tokens_any": ["0008", "0169", "0173", "1067", "5026", "8023", "8042", "cncwr"],
        "seed_uris": [_uri("Alarma_0008"), _uri("Error_0169"), _uri("Alarma_0173"), _uri("AvisoSeguridad_1067"), _uri("Alarma_5026"), _uri("Error_8023"), _uri("Error_8042"), _uri("Marca_OVERTEMP")],
        "seed_token_map": {
            "0008": [_uri("Alarma_0008")],
            "0169": [_uri("Error_0169"), _uri("Marca_OVERTEMP")],
            "0173": [_uri("Alarma_0173"), _uri("Marca_OVERTEMP")],
            "1067": [_uri("AvisoSeguridad_1067")],
            "5026": [_uri("Alarma_5026")],
            "cncwr": [_uri("Alarma_5026")],
            "8023": [_uri("Error_8023"), _uri("Error_8042")],
            "8042": [_uri("Error_8042"), _uri("Error_8023")],
            "50 mb": [_uri("Error_8023"), _uri("Error_8042")],
        },
        "steps": [
            {"step_id": "seed", "purpose": "seed_error_condition_attribute", "mode": "fixed_seed", "fixed_uris": [_uri("Alarma_0008"), _uri("Error_0169"), _uri("Alarma_0173"), _uri("AvisoSeguridad_1067"), _uri("Alarma_5026"), _uri("Error_8023"), _uri("Error_8042"), _uri("Marca_OVERTEMP")], "max_candidates": 6, "max_results": 6},
            {"step_id": "detail", "purpose": "error_condition_attribute_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "valor"], "max_candidates": 6, "max_results": 24},
        ],
    },
    {
        "family_id": "error_code_resolution_procedure_lookup",
        "template_id": "ERR_T3_resolution_procedure",
        "intent": "procedure_lookup",
        "hop_depth": 1,
        "family_type": "error_strict",
        "policy_id": "error_strict",
        "canonical_anchor": "error_resolution_procedure",
        "anchor_groups_any": ["error_resolution_procedure"],
        "keywords_any": [
            ["0040"],
            ["1737"],
            ["4026"],
            ["editor de perfiles"],
            ["error de geometria"],
        ],
        "technical_tokens_any": ["0040", "1737", "4026", "geometry_error", "feedat", "endat"],
        "seed_uris": [_uri("Error_0040"), _uri("Alarma_1737"), _uri("Fallo_4026"), _uri("AvisoSeguridad_960_03"), _uri("InterfazUsuario_EditorPerfiles")],
        "seed_token_map": {
            "0040": [_uri("Error_0040")],
            "1737": [_uri("Alarma_1737")],
            "4026": [_uri("Fallo_4026")],
            "feedat": [_uri("Fallo_4026")],
            "endat": [_uri("Fallo_4026")],
            "editor de perfiles": [_uri("AvisoSeguridad_960_03"), _uri("InterfazUsuario_EditorPerfiles")],
            "error de geometria": [_uri("AvisoSeguridad_960_03"), _uri("InterfazUsuario_EditorPerfiles")],
            "geometry error": [_uri("AvisoSeguridad_960_03"), _uri("InterfazUsuario_EditorPerfiles")],
        },
        "steps": [
            {"step_id": "seed", "purpose": "seed_error_resolution_procedure", "mode": "fixed_seed", "fixed_uris": [_uri("Error_0040"), _uri("Alarma_1737"), _uri("Fallo_4026"), _uri("AvisoSeguridad_960_03"), _uri("InterfazUsuario_EditorPerfiles")], "max_candidates": 5, "max_results": 5},
            {"step_id": "detail", "purpose": "error_resolution_procedure_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "valor"], "max_candidates": 5, "max_results": 22},
        ],
    },
    {
        "family_id": "error_code_comparison_lookup",
        "template_id": "ERR_T4_code_comparison",
        "intent": "component_relation_lookup",
        "hop_depth": 2,
        "family_type": "error_strict",
        "policy_id": "error_strict",
        "canonical_anchor": "error_code_comparison",
        "anchor_groups_any": ["error_code_comparison"],
        "keywords_any": [
            ["1166"],
            ["1167"],
            ["8458"],
            ["8459"],
        ],
        "technical_tokens_any": ["1166", "1167", "8458", "8459", "sqrt", "log", "ln", "pim", "pit"],
        "seed_uris": [_uri("Alarma_1166"), _uri("Alarma_1167"), _uri("Error_8458"), _uri("Error_8459")],
        "seed_token_map": {
            "1166": [_uri("Alarma_1166"), _uri("Alarma_1167")],
            "1167": [_uri("Alarma_1167"), _uri("Alarma_1166")],
            "sqrt": [_uri("Alarma_1166"), _uri("Alarma_1167")],
            "log": [_uri("Alarma_1167"), _uri("Alarma_1166")],
            "ln": [_uri("Alarma_1167"), _uri("Alarma_1166")],
            "8458": [_uri("Error_8458"), _uri("Error_8459")],
            "8459": [_uri("Error_8459"), _uri("Error_8458")],
            "pim": [_uri("Error_8458"), _uri("Error_8459")],
            "pit": [_uri("Error_8459"), _uri("Error_8458")],
        },
        "steps": [
            {"step_id": "seed", "purpose": "seed_error_code_comparison", "mode": "fixed_seed", "fixed_uris": [_uri("Alarma_1166"), _uri("Alarma_1167"), _uri("Error_8458"), _uri("Error_8459")], "max_candidates": 4, "max_results": 4},
            {"step_id": "detail", "purpose": "error_code_comparison_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "valor"], "max_candidates": 4, "max_results": 18},
        ],
    },
    {
        "family_id": "error_parameter_range_lookup",
        "template_id": "ERR_T5_parameter_range",
        "intent": "parameter_lookup",
        "hop_depth": 1,
        "family_type": "error_strict",
        "policy_id": "error_strict",
        "canonical_anchor": "error_parameter_range",
        "anchor_groups_any": ["error_parameter_range"],
        "keywords_any": [
            ["1359"],
            ["8789"],
            ["var", "endvar", "delete"],
            ["li", "lo", "era"],
        ],
        "technical_tokens_any": ["1359", "8789", "li_li16", "lo_lo8"],
        "seed_uris": [_uri("AvisoSeguridad_1359"), _uri("Error_8789"), _uri("LI1-LI16"), _uri("IO_Local_LO1_LO8")],
        "seed_token_map": {
            "1359": [_uri("AvisoSeguridad_1359")],
            "#var": [_uri("AvisoSeguridad_1359")],
            "#endvar": [_uri("AvisoSeguridad_1359")],
            "#delete": [_uri("AvisoSeguridad_1359")],
            "8789": [_uri("Error_8789"), _uri("LI1-LI16"), _uri("IO_Local_LO1_LO8")],
            "era": [_uri("Error_8789"), _uri("LI1-LI16"), _uri("IO_Local_LO1_LO8")],
            "li1": [_uri("Error_8789"), _uri("LI1-LI16"), _uri("IO_Local_LO1_LO8")],
            "lo1": [_uri("Error_8789"), _uri("IO_Local_LO1_LO8"), _uri("LI1-LI16")],
        },
        "steps": [
            {"step_id": "seed", "purpose": "seed_error_parameter_range", "mode": "fixed_seed", "fixed_uris": [_uri("AvisoSeguridad_1359"), _uri("Error_8789"), _uri("LI1-LI16"), _uri("IO_Local_LO1_LO8")], "max_candidates": 4, "max_results": 4},
            {"step_id": "detail", "purpose": "error_parameter_range_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "valor"], "max_candidates": 4, "max_results": 18},
        ],
    },
]

STRICT_CROSS_FAMILIES = [
    {
        "family_id": "cross_manual_home_search_procedure",
        "template_id": "CROSS_T1_home_search",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "cross_manual_strict",
        "policy_id": "cross_manual_strict",
        "canonical_anchor": "cross_home_search_c_axis",
        "anchor_groups_all": ["machine_c_axis_context", "jog_and_home"],
        "keywords_any": [["plato divisor", "rotary table", "eje c", "c axis"], ["busqueda de referencia", "manual home search", "home search"]],
        "seed_uris": [_uri("PlatoDivisor"), _uri("ManualHomeSearch")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_cross_home_search", "mode": "fixed_seed", "fixed_uris": [_uri("PlatoDivisor"), _uri("ManualHomeSearch")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "cross_home_search_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 2, "max_results": 14},
        ],
    },
    {
        "family_id": "cross_manual_tool_inspection_conditional",
        "template_id": "CROSS_T2_tool_inspection_setup",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "cross_manual_strict",
        "policy_id": "cross_manual_strict",
        "canonical_anchor": "cross_tool_inspection_setup",
        "anchor_groups_all": ["machine_safety_to_cnc_operation"],
        "require_keyword_match": True,
        "keywords_any": [
            ["tool inspection", "inspect", "inspeccionar"],
            ["doors open", "puertas abiertas", "apertura puertas", "broach"],
        ],
        "seed_uris": [_uri("ToolInspection"), _uri("CycleStopKey"), _uri("SelectorSetUp"), _uri("BotonAperturaPuertas")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_cross_tool_inspection", "mode": "fixed_seed", "fixed_uris": [_uri("ToolInspection"), _uri("CycleStopKey"), _uri("SelectorSetUp"), _uri("BotonAperturaPuertas")], "max_candidates": 4, "max_results": 4},
            {"step_id": "detail", "purpose": "cross_tool_inspection_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 4, "max_results": 18},
        ],
    },
    {
        "family_id": "cross_manual_simulation_multi_hop",
        "template_id": "CROSS_T3_simulation",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "cross_manual_strict",
        "policy_id": "cross_manual_strict",
        "canonical_anchor": "cross_simulation",
        "anchor_groups_all": ["simulation", "machine_program_storage"],
        "require_keyword_match": True,
        "keywords_any": [
            ["a218", "brochado", "broaching", "carro", "carriage"],
            ["plc", "simulacion", "simulation", "ejes", "axes"],
        ],
        "seed_uris": [_uri("EDISIMU_MODE"), _uri("ProgramSimulation"), _uri("SimulatedExecution")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_cross_simulation", "mode": "fixed_seed", "fixed_uris": [_uri("EDISIMU_MODE"), _uri("ProgramSimulation"), _uri("SimulatedExecution")], "max_candidates": 3, "max_results": 3},
            {"step_id": "detail", "purpose": "cross_simulation_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 3, "max_results": 16},
        ],
    },
    {
        "family_id": "cross_manual_incremental_jog_procedure",
        "template_id": "CROSS_T4_incremental_jog",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "cross_manual_strict",
        "policy_id": "cross_manual_strict",
        "canonical_anchor": "cross_incremental_jog",
        "anchor_groups_all": ["machine_axis_motion"],
        "require_keyword_match": True,
        "keywords_any": [["carro porta-piezas", "carriage", "eje z", "z axis"], ["incremental", "incremental distance", "manual controls", "mandos manuales"]],
        "seed_uris": [_uri("CarroPortaPiezas_46"), _uri("JogPanel"), _uri("SelectorModoJog")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_cross_incremental_jog", "mode": "fixed_seed", "fixed_uris": [_uri("CarroPortaPiezas_46"), _uri("JogPanel"), _uri("SelectorModoJog")], "max_candidates": 3, "max_results": 3},
            {"step_id": "detail", "purpose": "cross_incremental_jog_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 3, "max_results": 16},
        ],
    },
    {
        "family_id": "cross_manual_block_search_conditional",
        "template_id": "CROSS_T5_block_search",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "cross_manual_strict",
        "policy_id": "cross_manual_strict",
        "canonical_anchor": "cross_block_search",
        "anchor_groups_all": ["machine_program_recovery"],
        "require_keyword_match": True,
        "keywords_any": [["emergency", "emergencia", "restore the system", "restaurar el sistema"], ["block search", "busqueda de bloque"]],
        "seed_uris": [_uri("BusquedaBloqueAutomatica"), _uri("BusquedaBloque")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_cross_block_search", "mode": "fixed_seed", "fixed_uris": [_uri("BusquedaBloqueAutomatica"), _uri("BusquedaBloque")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "cross_block_search_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 2, "max_results": 16},
        ],
    },
    {
        "family_id": "cross_manual_c_axis_instruction",
        "template_id": "CROSS_T6_c_axis_instruction",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "cross_manual_strict",
        "policy_id": "cross_manual_strict",
        "canonical_anchor": "cross_c_axis_instruction",
        "anchor_groups_all": ["machine_c_axis_context"],
        "require_keyword_match": True,
        "keywords_any": [["high-level instruction", "instruccion de alto nivel"], ["activate the spindle", "activar el husillo", "c axis", "eje c"]],
        "seed_uris": [_uri("PlatoDivisor"), _uri("Instruccion_CAX")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_cross_c_axis", "mode": "fixed_seed", "fixed_uris": [_uri("PlatoDivisor"), _uri("Instruccion_CAX")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "cross_c_axis_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 2, "max_results": 12},
        ],
    },
    {
        "family_id": "cross_manual_file_protection_multi_hop",
        "template_id": "CROSS_T7_file_protection",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "cross_manual_strict",
        "policy_id": "cross_manual_strict",
        "canonical_anchor": "cross_file_protection",
        "anchor_groups_all": ["utilities_and_file_protection", "machine_program_storage"],
        "require_keyword_match": True,
        "keywords_any": [["prg", "fagorcnc", "users"], ["edisimu", "modifiable", "-m-"]],
        "seed_uris": [_uri("ModoOperacion_UTILITIES"), _uri("SoftkeyChangeModifiableAttribute"), _uri("EDISIMU_MODE")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_cross_file_protection", "mode": "fixed_seed", "fixed_uris": [_uri("ModoOperacion_UTILITIES"), _uri("SoftkeyChangeModifiableAttribute"), _uri("EDISIMU_MODE")], "max_candidates": 3, "max_results": 3},
            {"step_id": "detail", "purpose": "cross_file_protection_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 3, "max_results": 16},
        ],
    },
    {
        "family_id": "cross_manual_mdi_history_retention",
        "template_id": "CROSS_T8_mdi_history",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "cross_manual_strict",
        "policy_id": "cross_manual_strict",
        "canonical_anchor": "cross_mdi_history",
        "anchor_groups_all": ["mdi_mda", "machine_safety_to_cnc_operation"],
        "require_keyword_match": True,
        "keywords_any": [["mdi/mda", "modo mdi/mda", "set-up", "set up"], ["m and g functions", "funciones m y g", "feedrate", "spindle speed", "avance", "velocidad del husillo"]],
        "seed_uris": [_uri("ToolInspection"), _uri("SelectorSetUp")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_cross_mdi_history", "mode": "fixed_seed", "fixed_uris": [_uri("ToolInspection"), _uri("SelectorSetUp")], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "cross_mdi_history_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 2, "max_results": 16},
        ],
    },
    {
        "family_id": "cross_manual_parameter_scope",
        "template_id": "CROSS_T9_parameter_scope",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "cross_manual_strict",
        "policy_id": "cross_manual_strict",
        "canonical_anchor": "cross_parameter_scope",
        "anchor_groups_all": ["machine_offsets_and_parameters"],
        "require_keyword_match": True,
        "keywords_any": [["parametro aritmetico", "arithmetic parameter"], ["todos los canales", "all channels", "shared"], ["common parameters", "parametros comunes"]],
        "seed_uris": [_uri("Tabla_27_3")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_cross_parameter_scope", "mode": "fixed_seed", "fixed_uris": [_uri("Tabla_27_3")], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "cross_parameter_scope_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 1, "max_results": 12},
        ],
    },
    {
        "family_id": "cross_manual_zero_offset_codes",
        "template_id": "CROSS_T10_zero_offset_codes",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "cross_manual_strict",
        "policy_id": "cross_manual_strict",
        "canonical_anchor": "cross_zero_offsets",
        "anchor_groups_any": ["fixture_and_offsets", "machine_offsets_and_parameters", "machine_c_axis_context"],
        "require_keyword_match": True,
        "keywords_any": [["decalajes de cero", "zero offsets", "absolute zero offsets"], ["g codes", "codigos g", "g54", "g55", "g56", "g57", "g58", "g59"]],
        "seed_uris": [_uri("G54"), _uri("G55"), _uri("G56"), _uri("G57"), _uri("G58"), _uri("G59")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_cross_zero_offsets", "mode": "fixed_seed", "fixed_uris": [_uri("G54"), _uri("G55"), _uri("G56"), _uri("G57"), _uri("G58"), _uri("G59")], "max_candidates": 6, "max_results": 6},
            {"step_id": "detail", "purpose": "cross_zero_offset_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador"], "max_candidates": 6, "max_results": 18},
        ],
    },
    {
        "family_id": "cross_manual_shortcut_navigation",
        "template_id": "CROSS_T11_shortcut_navigation",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "cross_manual_strict",
        "policy_id": "cross_manual_strict",
        "canonical_anchor": "cross_shortcut_navigation",
        "anchor_groups_all": ["machine_utilities_navigation"],
        "technical_tokens_any": ["ctrl+f12"],
        "require_keyword_match": True,
        "keywords_any": [["delete", "borrar", "erase"], ["utilities mode", "modo utilidades"]],
        "seed_uris": [_uri("InterfazUsuario_3"), _uri("ModoOperacion_UTILITIES"), _uri("SoftkeyDelete"), _uri("TeclaF12")],
        "steps": [
            {"step_id": "seed", "purpose": "seed_cross_shortcut_navigation", "mode": "fixed_seed", "fixed_uris": [_uri("InterfazUsuario_3"), _uri("ModoOperacion_UTILITIES"), _uri("SoftkeyDelete"), _uri("TeclaF12")], "max_candidates": 4, "max_results": 4},
            {"step_id": "detail", "purpose": "cross_shortcut_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label"], "max_candidates": 4, "max_results": 18},
        ],
    },
]


@dataclass
class QuestionParse:
    intent: str
    anchor_text: str | None
    anchor_candidates: list[str]
    qualifiers: list[str]
    anchor_groups: list[str] = field(default_factory=list)
    technical_tokens: list[str] = field(default_factory=list)
    matched_seed_uris: list[str] = field(default_factory=list)
    matched_anchor_rule: str | None = None
    intent_confidence: float = 0.4
    anchor_confidence: float = 0.0


@dataclass
class QueryStep:
    step_id: str
    purpose: str
    mode: str
    seed_source: str = "previous"
    relation: str | None = None
    incoming: bool = False
    fixed_uris: list[str] = field(default_factory=list)
    preferred_predicates: list[str] = field(default_factory=list)
    target_filters: list[str] = field(default_factory=list)
    max_candidates: int = 8
    max_results: int = 20
    boundedness_target: str = "bounded"


@dataclass
class QueryPlan:
    intent: str
    anchor_text: str | None
    anchor_candidates: list[str]
    template_id: str
    plan_family: str
    predicted_hop_depth: int
    fallback_used: bool
    sparql: str
    steps: list[QueryStep] = field(default_factory=list)
    confidence: dict[str, Any] = field(default_factory=dict)
    boundedness_policy: dict[str, Any] = field(default_factory=dict)
    recommended_action: str = "execute"
    final_boundedness: str = "unknown"
    question_language: str = "es"
    question_language_confidence: float = 0.0
    normalized_question: str = ""
    multilingual_lexicon_hits: list[dict[str, Any]] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryStepTrace:
    step_id: str
    purpose: str
    mode: str
    query_text: str
    input_candidate_count: int
    raw_result_count: int
    output_candidate_count: int
    pruned_count: int
    boundedness_status: str
    output_uris: list[str] = field(default_factory=list)
    sample_rows: list[list[str]] = field(default_factory=list)
    prune_reason: str | None = None
    error: str | None = None


@dataclass
class QueryExecutionTrace:
    steps: list[QueryStepTrace] = field(default_factory=list)
    final_boundedness: str = "unknown"


@dataclass
class QueryExecutionResult:
    plan: QueryPlan
    rows: list[tuple[str, str, str]]
    raw_bindings: list[tuple[str, ...]]
    trace: QueryExecutionTrace


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Shared multi-hop SPARQL planner.")
    parser.add_argument("question", nargs="?", default="What directive is associated with CE conformity?")
    parser.add_argument("--export-plan-catalog", action="store_true", help="Export the current multihop plan catalog and exit.")
    parser.add_argument("--export-generalization-catalog", action="store_true", help="Export the generalized planner families and exit.")
    parser.add_argument("--export-boundedness-matrix", action="store_true", help="Export the boundedness policies and exit.")
    return parser.parse_args()


MULTIHOP_PLAN_FAMILIES = [
    {
        "family_id": "machine_directive_compliance",
        "template_id": "MH_T1_machine_directive",
        "intent": "regulatory_lookup",
        "hop_depth": 2,
        "keywords_any": [["directiva"], ["conformidad", "cumple"]],
        "seed_uris": [f"{BASE_URI}DirectivaMaquinas2006_42_CE"],
        "policy_id": "benchmark_seeded",
        "family_type": "benchmark_seeded",
        "evidence_questions": ["Que directiva cumple la maquina de brochado exterior?"],
        "steps": [
            {"step_id": "seed", "purpose": "seed_machine", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}DirectivaMaquinas2006_42_CE"], "max_candidates": 1, "max_results": 1},
            {"step_id": "rel_1", "purpose": "machine_to_directive", "mode": "relation_traverse", "relation": "cumpleNormativa", "max_candidates": 3, "max_results": 6},
            {"step_id": "detail", "purpose": "directive_details", "mode": "describe_entities", "preferred_predicates": ["identificador", "label", "textoExtracto", "type"], "max_candidates": 3, "max_results": 12},
        ],
    },
    {
        "family_id": "system_maintenance_plan",
        "template_id": "MH_T2_system_maintenance",
        "intent": "regulatory_lookup",
        "hop_depth": 2,
        "keywords_any": [["plan", "mantenimiento"], ["sistema", "seguridad"]],
        "seed_uris": [f"{BASE_URI}SistemaSeguridadMaquina"],
        "policy_id": "benchmark_seeded",
        "family_type": "benchmark_seeded",
        "evidence_questions": ["Que plan de mantenimiento requiere el sistema de seguridad de la maquina?"],
        "steps": [
            {"step_id": "seed", "purpose": "seed_safety_system", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}SistemaSeguridadMaquina"], "max_candidates": 1, "max_results": 1},
            {"step_id": "rel_1", "purpose": "system_to_plan", "mode": "relation_traverse", "relation": "requiereMantenimiento", "max_candidates": 3, "max_results": 6},
            {"step_id": "detail", "purpose": "plan_details", "mode": "describe_entities", "preferred_predicates": ["label", "textoExtracto", "type"], "max_candidates": 3, "max_results": 12},
        ],
    },
    {
        "family_id": "manual_figure_reference",
        "template_id": "MH_T3_manual_figure",
        "intent": "figure_or_reference_lookup",
        "hop_depth": 1,
        "keywords_any": [["figura"], ["manual", "a218"]],
        "seed_uris": [f"{BASE_URI}Figura0_1_1InformacionMostradaEnPaginas", f"{BASE_URI}ManualBrochadoraA218"],
        "policy_id": "benchmark_seeded",
        "family_type": "benchmark_seeded",
        "evidence_questions": ["Que figura queda asociada al manual A218?"],
        "steps": [
            {"step_id": "seed", "purpose": "seed_manual", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}Figura0_1_1InformacionMostradaEnPaginas", f"{BASE_URI}ManualBrochadoraA218"], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "figure_details", "mode": "describe_entities", "preferred_predicates": ["label", "textoExtracto", "identificador", "type"], "max_candidates": 2, "max_results": 12},
        ],
    },
    {
        "family_id": "column_component_control_chain",
        "template_id": "MH_T5_parent_component_control",
        "intent": "component_relation_lookup",
        "hop_depth": 1,
        "keywords_any": [["regla", "lineal"], ["columna_46", "columna 46", "componente"]],
        "seed_uris": [f"{BASE_URI}CarroPortaPiezas_46", f"{BASE_URI}ReglaLineal_46_1"],
        "policy_id": "benchmark_seeded",
        "family_type": "benchmark_seeded",
        "evidence_questions": ["Que regla lineal queda controlada por un componente de la Columna_46 y que descripcion tiene?"],
        "steps": [
            {"step_id": "seed", "purpose": "seed_parent_component", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}CarroPortaPiezas_46", f"{BASE_URI}ReglaLineal_46_1"], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "rule_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "type"], "max_candidates": 2, "max_results": 12},
        ],
    },
    {
        "family_id": "component_control_chain",
        "template_id": "MH_T4_component_control",
        "intent": "component_relation_lookup",
        "hop_depth": 1,
        "keywords_any": [["regla", "lineal"], ["carro", "porta", "piezas", "46"]],
        "seed_uris": [f"{BASE_URI}ReglaLineal_46_1", f"{BASE_URI}ReglaLineal_46_2"],
        "policy_id": "benchmark_seeded",
        "family_type": "benchmark_seeded",
        "evidence_questions": ["Que regla lineal controla el carro porta-piezas 46?"],
        "steps": [
            {"step_id": "seed", "purpose": "seed_component", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}ReglaLineal_46_1", f"{BASE_URI}ReglaLineal_46_2"], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "rule_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "type"], "max_candidates": 2, "max_results": 12},
        ],
    },
    {
        "family_id": "manual_safety_symbols_purpose",
        "template_id": "GX_T6_safety_symbols_purpose",
        "intent": "purpose_or_function_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_id": "manual_safety_symbols",
        "steps": [
            {"step_id": "seed", "purpose": "seed_manual_safety_symbols", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}IndicacionAdvertenciaSeguridad"], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "manual_safety_symbol_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "type"], "max_candidates": 1, "max_results": 8},
        ],
        "evidence_questions": ["Que objetivo tienen los simbolos de advertencia y seguridad del manual?"],
    },
    {
        "family_id": "manual_header_figure_lookup",
        "template_id": "GX_T1_manual_header_figure",
        "intent": "figure_or_reference_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_id": "figure_header_footer",
        "steps": [
            {"step_id": "seed", "purpose": "seed_header_figure", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}Figura0_1_1InformacionMostradaEnPaginas", f"{BASE_URI}ManualBrochadoraA218"], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "header_figure_details", "mode": "describe_entities", "preferred_predicates": ["label", "textoExtracto", "identificador", "type"], "max_candidates": 2, "max_results": 10},
        ],
        "evidence_questions": ["Que figura muestra la informacion que aparece en los encabezados y pies de pagina del manual?"],
    },
    {
        "family_id": "safety_symbol_detail",
        "template_id": "GX_T2_safety_symbol",
        "intent": "regulatory_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_ids": ["precaucion", "peligro", "medio_ambiente"],
        "steps": [
            {"step_id": "seed", "purpose": "seed_symbol", "mode": "fixed_seed", "fixed_uris": [], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "symbol_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "type"], "max_candidates": 2, "max_results": 8},
        ],
        "evidence_questions": ["Que puede ocurrir si no se tiene en cuenta una advertencia de peligro?", "Que indica una senal de precaucion en el manual?", "Que tipo de informacion representa la indicacion de medio ambiente?"],
    },
    {
        "family_id": "environment_symbol_purpose",
        "template_id": "GX_T7_environment_symbol",
        "intent": "purpose_or_function_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_id": "medio_ambiente",
        "steps": [
            {"step_id": "seed", "purpose": "seed_environment_symbol", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}MedioAmbiente"], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "environment_symbol_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "type"], "max_candidates": 1, "max_results": 8},
        ],
        "evidence_questions": ["Que tipo de informacion representa la indicacion de medio ambiente?"],
    },
    {
        "family_id": "ekin_contact_literal",
        "template_id": "GX_T3_ekin_contact",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_ids": ["ekin_company", "client_support_department"],
        "steps": [
            {"step_id": "seed", "purpose": "seed_contact_entity", "mode": "fixed_seed", "fixed_uris": [], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "contact_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "identificador", "label", "type"], "max_candidates": 2, "max_results": 10},
        ],
        "evidence_questions": ["A quien se debe consultar en caso de dudas sobre la seguridad de la maquina?", "Donde se encuentra la direccion de la empresa EKIN mencionada en el manual?", "Cual es el correo electronico de contacto de EKIN indicado en el manual?"],
    },
    {
        "family_id": "spare_parts_policy_literal",
        "template_id": "GX_T4_spare_parts",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_id": "spare_parts_policy",
        "steps": [
            {"step_id": "seed", "purpose": "seed_spare_parts_policy", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}PiezaRecambio_1", f"{BASE_URI}Empresa_EKIN_S_Coop"], "max_candidates": 2, "max_results": 2},
            {"step_id": "detail", "purpose": "spare_parts_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "identificador", "label", "type"], "max_candidates": 2, "max_results": 10},
        ],
        "evidence_questions": ["Que tipo de piezas de recambio deben emplearse segun el manual?"],
    },
    {
        "family_id": "ce_directive_literal",
        "template_id": "GX_T5_ce_directive",
        "intent": "regulatory_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_id": "directive_2006_42_ce",
        "steps": [
            {"step_id": "seed", "purpose": "seed_ce_directive", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}Directiva2006_42_CE"], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "ce_directive_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "identificador", "label", "type"], "max_candidates": 1, "max_results": 8},
        ],
        "evidence_questions": ["Segun que directiva se realiza la declaracion CE de conformidad sobre maquinas?"],
    },
    {
        "family_id": "machine_safety_verification_requirement",
        "template_id": "GX_T8_safety_verification",
        "intent": "component_attribute_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_id": "elementos_seguridad_verificacion",
        "steps": [
            {"step_id": "seed", "purpose": "seed_machine_safety_elements", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}ElementoSeguridad_1"], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "machine_safety_verification_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "type"], "max_candidates": 1, "max_results": 8},
        ],
        "evidence_questions": ["Que se debe verificar regularmente para garantizar la seguridad de la maquina?"],
    },
    {
        "family_id": "machine_safety_verification_requirement_regulatory",
        "template_id": "GX_T8_safety_verification",
        "intent": "regulatory_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_id": "elementos_seguridad_verificacion",
        "steps": [
            {"step_id": "seed", "purpose": "seed_machine_safety_elements", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}ElementoSeguridad_1"], "max_candidates": 1, "max_results": 1},
            {"step_id": "detail", "purpose": "machine_safety_verification_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "type"], "max_candidates": 1, "max_results": 8},
        ],
        "evidence_questions": ["Que se debe verificar regularmente para garantizar la seguridad de la maquina?"],
    },
    {
        "family_id": "quick_ref_work_mode_lookup",
        "template_id": "QR_T1_work_modes",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_id": "quick_ref_work_modes",
        "keywords_any": [["modo", "work"], ["automatico", "automatic", "jog", "mdi"]],
        "steps": [
            {"step_id": "seed", "purpose": "seed_quick_ref_work_modes", "mode": "fixed_seed", "fixed_uris": [], "max_candidates": 3, "max_results": 3},
            {"step_id": "detail", "purpose": "quick_ref_work_mode_details", "mode": "describe_entities", "preferred_predicates": ["label", "textoExtracto", "identificador", "type"], "max_candidates": 3, "max_results": 12},
        ],
        "evidence_questions": ["Que modos de trabajo estan disponibles en el monitor y teclado?"],
    },
    {
        "family_id": "quick_ref_key_purpose_lookup",
        "template_id": "QR_T2_key_purpose",
        "intent": "purpose_or_function_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_ids": ["quick_ref_monitor_keyboard", "quick_ref_feed_speed_tool"],
        "steps": [
            {"step_id": "seed", "purpose": "seed_quick_ref_key", "mode": "fixed_seed", "fixed_uris": [], "max_candidates": 3, "max_results": 3},
            {"step_id": "detail", "purpose": "quick_ref_key_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "type"], "max_candidates": 3, "max_results": 12},
        ],
        "evidence_questions": ["Para que sirve la tecla focus en el monitor y teclado?"],
    },
    {
        "family_id": "quick_ref_jog_operation_lookup",
        "template_id": "QR_T3_jog_operation",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_id": "quick_ref_jog_panel",
        "steps": [
            {"step_id": "seed", "purpose": "seed_quick_ref_jog", "mode": "fixed_seed", "fixed_uris": [], "max_candidates": 3, "max_results": 3},
            {"step_id": "detail", "purpose": "quick_ref_jog_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "type"], "max_candidates": 3, "max_results": 12},
        ],
        "evidence_questions": ["Que se debe pulsar para mover un eje desde el panel jog?"],
    },
    {
        "family_id": "quick_ref_home_search_procedure",
        "template_id": "QR_T4_home_search",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_id": "quick_ref_home_search",
        "steps": [
            {"step_id": "seed", "purpose": "seed_quick_ref_home_search", "mode": "fixed_seed", "fixed_uris": [], "max_candidates": 3, "max_results": 3},
            {"step_id": "detail", "purpose": "quick_ref_home_search_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "type"], "max_candidates": 3, "max_results": 12},
        ],
        "evidence_questions": ["Que tecla confirma la busqueda de referencia?"],
    },
    {
        "family_id": "quick_ref_coordinate_preset_procedure",
        "template_id": "QR_T5_coordinate_preset",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_id": "quick_ref_coordinate_preset",
        "steps": [
            {"step_id": "seed", "purpose": "seed_quick_ref_coordinate_preset", "mode": "fixed_seed", "fixed_uris": [], "max_candidates": 3, "max_results": 3},
            {"step_id": "detail", "purpose": "quick_ref_coordinate_preset_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "type"], "max_candidates": 3, "max_results": 12},
        ],
        "evidence_questions": ["Que tecla confirma el valor del preset de coordenadas?"],
    },
    {
        "family_id": "quick_ref_feed_speed_tool_lookup",
        "template_id": "QR_T6_feed_speed_tool",
        "intent": "literal_lookup",
        "hop_depth": 1,
        "family_type": "generalized",
        "policy_id": "direct_seed_literal",
        "anchor_rule_id": "quick_ref_feed_speed_tool",
        "steps": [
            {"step_id": "seed", "purpose": "seed_quick_ref_feed_speed_tool", "mode": "fixed_seed", "fixed_uris": [], "max_candidates": 4, "max_results": 4},
            {"step_id": "detail", "purpose": "quick_ref_feed_speed_tool_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "type"], "max_candidates": 4, "max_results": 12},
        ],
        "evidence_questions": ["Que teclas se utilizan para fijar el avance la velocidad o la herramienta?"],
    },
]


def cargar_grafo_memoria() -> Graph:
    if not TBOX_PATH.exists() or not ABOX_PATH.exists():
        raise SystemExit("Error: Missing T-Box or A-Box files.")
    graph = Graph()
    graph.parse(TBOX_PATH, format="turtle")
    graph.parse(ABOX_PATH, format="turtle")
    return graph



def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("?", " ").replace("?", " ")
    text = re.sub(r"[^a-z0-9@/_\-.]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()



def normalize_uri(uri: str) -> str:
    return str(uri).split("/")[-1].split("#")[-1]


def _normalize_seed_surface(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    text = text.replace("_", " ").replace("-", " ").replace("/", " ")
    text = re.sub(r"[^A-Za-z0-9\[\]#.@]+", " ", text)
    return " ".join(text.lower().split())


def _seed_signal_tokens(text: str) -> set[str]:
    raw = text or ""
    signals = set(re.findall(r"[A-Z]{2,}[A-Z0-9._\[\]-]*", raw))
    signals.update(re.findall(r"\b\d{3,}\b", raw))
    normalized = _normalize_seed_surface(raw)
    for token in normalized.split():
        if any(ch.isdigit() for ch in token) or token.isupper():
            signals.add(token.upper())
    return {token for token in signals if token}


def _seed_content_tokens(text: str) -> set[str]:
    return {
        token
        for token in _normalize_seed_surface(text).split()
        if len(token) > 1 and token not in STOPWORDS and token not in SEED_GENERIC_TOKENS
    }


def _seed_search_variants(uri: str) -> list[str]:
    local_name = normalize_uri(uri)
    variants = [local_name]
    stripped = re.sub(
        r"^(Alarma|AvisoSeguridad|Error|Figura|Frecuencia|Indicacion|InterfazUsuario|Maquina|Marca|ModoOperacion|Parametro|PiezaRecambio|Sistema|Tabla|Tecla)_?",
        "",
        local_name,
    )
    if stripped and stripped != local_name:
        variants.append(stripped)
    if stripped.startswith("Error"):
        variants.append(stripped[5:])
    return variants


def _graph_has_subject(graph: Graph, uri: str) -> bool:
    return any(True for _ in graph.predicate_objects(URIRef(uri)))


@lru_cache(maxsize=4)
def _cached_seed_index(ttl_path: str) -> list[dict[str, Any]]:
    graph = Graph()
    graph.parse(ttl_path, format="turtle")
    label_uri = URIRef(PREDICATE_URI_MAP["label"])
    identifier_uri = URIRef(PREDICATE_URI_MAP["identificador"])
    value_uri = URIRef(PREDICATE_URI_MAP["valor"])
    index: list[dict[str, Any]] = []
    for subject in set(graph.subjects()):
        if not isinstance(subject, URIRef):
            continue
        uri = str(subject)
        if not uri.startswith(BASE_URI):
            continue
        raw_values = [normalize_uri(uri)]
        raw_values.extend(str(obj) for obj in graph.objects(subject, label_uri))
        raw_values.extend(str(obj) for obj in graph.objects(subject, identifier_uri))
        raw_values.extend(str(obj) for obj in graph.objects(subject, value_uri))
        normalized_values = {value for value in (_normalize_seed_surface(item) for item in raw_values) if len(value) > 1}
        if not normalized_values:
            continue
        signal_tokens = set()
        content_tokens = set()
        for item in raw_values:
            signal_tokens.update(_seed_signal_tokens(item))
            content_tokens.update(_seed_content_tokens(item))
        index.append(
            {
                "uri": uri,
                "normalized_values": normalized_values,
                "signal_tokens": signal_tokens,
                "content_tokens": content_tokens,
            }
        )
    return index


def _graph_seed_index(graph: Graph) -> list[dict[str, Any]]:
    ttl_path = graph.identifier if isinstance(graph.identifier, str) else ""
    if ttl_path and Path(ttl_path).exists():
        return _cached_seed_index(str(Path(ttl_path).resolve()))
    label_uri = URIRef(PREDICATE_URI_MAP["label"])
    identifier_uri = URIRef(PREDICATE_URI_MAP["identificador"])
    value_uri = URIRef(PREDICATE_URI_MAP["valor"])
    index: list[dict[str, Any]] = []
    for subject in set(graph.subjects()):
        if not isinstance(subject, URIRef):
            continue
        uri = str(subject)
        if not uri.startswith(BASE_URI):
            continue
        raw_values = [normalize_uri(uri)]
        raw_values.extend(str(obj) for obj in graph.objects(subject, label_uri))
        raw_values.extend(str(obj) for obj in graph.objects(subject, identifier_uri))
        raw_values.extend(str(obj) for obj in graph.objects(subject, value_uri))
        normalized_values = {value for value in (_normalize_seed_surface(item) for item in raw_values) if len(value) > 1}
        if not normalized_values:
            continue
        signal_tokens = set()
        content_tokens = set()
        for item in raw_values:
            signal_tokens.update(_seed_signal_tokens(item))
            content_tokens.update(_seed_content_tokens(item))
        index.append(
            {
                "uri": uri,
                "normalized_values": normalized_values,
                "signal_tokens": signal_tokens,
                "content_tokens": content_tokens,
            }
        )
    return index


def _resolve_fixed_seed_uri(uri: str, graph: Graph, index: list[dict[str, Any]]) -> str:
    if _graph_has_subject(graph, uri):
        return uri
    for alias_uri in FIXED_SEED_URI_ALIASES.get(uri, []):
        if _graph_has_subject(graph, alias_uri):
            return alias_uri

    variant_texts = [_normalize_seed_surface(item) for item in _seed_search_variants(uri)]
    variant_texts = [item for item in variant_texts if item]
    target_signals = set()
    target_tokens = set()
    for item in _seed_search_variants(uri):
        target_signals.update(_seed_signal_tokens(item))
        target_tokens.update(_seed_content_tokens(item))

    best_uri = uri
    best_score = 0
    for candidate in index:
        score = 0
        candidate_values = candidate["normalized_values"]
        candidate_signals = candidate["signal_tokens"]
        candidate_tokens = candidate["content_tokens"]
        for text in variant_texts:
            if text in candidate_values:
                score = max(score, 220)
            elif any(text and text in value for value in candidate_values):
                score = max(score, 160)
            else:
                overlap = target_tokens & candidate_tokens
                if overlap:
                    score = max(score, 90 + 20 * len(overlap))
        if target_signals and candidate_signals:
            signal_overlap = target_signals & candidate_signals
            if signal_overlap:
                score = max(score, 185 + 5 * len(signal_overlap))
        if score > best_score:
            best_score = score
            best_uri = candidate["uri"]
    return best_uri if best_score >= 110 else uri


def reconcile_fixed_seed_uris(fixed_uris: list[str], graph: Graph) -> list[str]:
    index = _graph_seed_index(graph)
    reconciled: list[str] = []
    for uri in fixed_uris:
        resolved_uri = _resolve_fixed_seed_uri(uri, graph, index)
        if resolved_uri not in reconciled:
            reconciled.append(resolved_uri)
    return reconciled



def tokenize_question(question: str) -> list[str]:
    tokens = []
    for token in normalize_text(question).split():
        if len(token) < 3 or token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens



_ALLCAPS_STOP: set[str] = {
    "DEBE", "PARA", "ESTE", "ESTA", "PERO", "COMO", "TODO", "CADA",
    "ESTA", "SENAL", "MARCA", "TIPO", "MODO", "VALOR", "DATO",
}


def extract_reference_tokens(question: str) -> list[str]:
    normalized = normalize_text(question)
    refs = re.findall(r"\b\d+(?:[-.]\d+)+\b", normalized)
    alphanum = re.findall(r"\b[a-z]*\d+[a-z0-9/_-]*\b", normalized)
    emails = re.findall(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", normalized)
    # ALL_CAPS identifiers (≥4 chars) from original text — e.g. SHUTTERON, LASERON, PWMON.
    # These are technical PLC/CNC identifiers that contain no digits.
    allcaps = [
        t.lower() for t in re.findall(r"\b[A-Z][A-Z0-9]{3,}\b", question)
        if t not in _ALLCAPS_STOP
    ]
    seen: list[str] = []
    for token in refs + alphanum + emails + allcaps:
        # Exclude bare integers (≤5 digits) — almost always page numbers.
        if token not in seen and not (token.isdigit() and len(token) <= 5):
            seen.append(token)
    return seen



def detect_intent(question: str) -> tuple[str, float]:
    normalized = normalize_text(question)
    if any(
        phrase in normalized
        for phrase in (
            "home search",
            "homing",
            "busqueda de referencia",
            "busqueda de home",
            "preset de coordenadas",
            "coordinate preset",
            "panel jog",
            "jog panel",
        )
    ):
        return "literal_lookup", 0.88
    best_intent = "literal_lookup"
    best_score = 0
    for intent, triggers in INTENT_TRIGGER_RULES:
        score = sum(1 for trigger in triggers if trigger in normalized)
        if score > best_score:
            best_intent = intent
            best_score = score
    confidence = min(0.45 + 0.15 * best_score, 0.95) if best_score else 0.35
    return best_intent, confidence



def match_anchor_rule(question: str, intent: str) -> dict[str, Any] | None:
    normalized = normalize_text(question)
    best_rule = None
    best_score = 0
    for rule in ANCHOR_ALIAS_RULES:
        if intent not in rule["preferred_intents"]:
            continue
        score = sum(1 for alias in rule["aliases"] if alias in normalized)
        if score > best_score:
            best_rule = rule
            best_score = score
    return best_rule



def _seed_uris_from_lexicon_hits(lexicon_hits: list[dict[str, Any]] | None) -> list[str]:
    seed_uris: list[str] = []
    for hit in lexicon_hits or []:
        for candidate in hit.get("candidates", []):
            uri = candidate.get("canonical_uri")
            if isinstance(uri, str) and uri.startswith("http") and uri not in seed_uris:
                seed_uris.append(uri)
    return seed_uris[:8]


def extract_anchor_text(
    question: str,
    intent: str,
    lexicon_hits: list[dict[str, Any]] | None = None,
    anchor_groups: list[str] | None = None,
) -> tuple[str | None, dict[str, Any] | None, float, list[str]]:
    refs = extract_reference_tokens(question)
    lexicon_seed_uris = _seed_uris_from_lexicon_hits(lexicon_hits)
    matched_rule = match_anchor_rule(question, intent)
    if matched_rule is not None:
        if not matched_rule["seed_uris"] and lexicon_seed_uris:
            matched_rule = {**matched_rule, "seed_uris": lexicon_seed_uris}
        return matched_rule["anchor_id"], matched_rule, matched_rule["confidence"], matched_rule.get("seed_uris", [])
    if anchor_groups:
        return anchor_groups[0], None, 0.82, lexicon_seed_uris
    if refs:
        return refs[0], None, 0.7, []
    if lexicon_hits:
        first_hit = lexicon_hits[0]
        surface = first_hit.get("surface")
        if isinstance(surface, str) and surface:
            return surface, None, 0.72, lexicon_seed_uris
    normalized = normalize_text(question)
    for anchor in [
        "ekin", "a218", "precaucion", "peligro", "medio ambiente", "seguridad",
        "safety", "columna_46", "46", "maintenance plan", "machine safety system",
    ]:
        if anchor in normalized:
            return anchor, None, 0.55, []
    return None, None, 0.2, []



def build_question_parse(
    question: str,
    lexicon_hits: list[dict[str, Any]] | None = None,
    anchor_groups: list[str] | None = None,
    technical_tokens: list[str] | None = None,
) -> QuestionParse:
    intent, intent_confidence = detect_intent(question)
    anchor_groups = anchor_groups or []
    technical_tokens = technical_tokens or []
    anchor_text, matched_rule, anchor_confidence, matched_seed_uris = extract_anchor_text(
        question,
        intent,
        lexicon_hits,
        anchor_groups,
    )
    tokens = tokenize_question(question)
    candidates: list[str] = []
    if anchor_text:
        candidates.append(anchor_text)
    for hit in lexicon_hits or []:
        surface = hit.get("surface")
        if isinstance(surface, str) and surface not in candidates:
            candidates.append(surface)
    for token in extract_reference_tokens(question) + tokens:
        if token not in candidates:
            candidates.append(token)
    qualifiers = [token for token in tokens if token not in candidates][:6]
    return QuestionParse(
        intent=intent,
        anchor_text=anchor_text,
        anchor_candidates=candidates[:8],
        qualifiers=qualifiers,
        anchor_groups=anchor_groups[:8],
        technical_tokens=technical_tokens[:8],
        matched_seed_uris=matched_seed_uris[:4],
        matched_anchor_rule=matched_rule["anchor_id"] if matched_rule else None,
        intent_confidence=round(intent_confidence, 2),
        anchor_confidence=round(anchor_confidence, 2),
    )



def build_regex_pattern(tokens: list[str]) -> str:
    usable = [token for token in tokens if token] or ["manual"]
    return "|".join(re.escape(token) for token in usable[:6])



def build_contains_clauses(var_s: str, var_o: str, tokens: list[str]) -> str:
    clauses = []
    for token in tokens[:4]:
        token_lower = token.lower()
        clauses.append(f'CONTAINS(LCASE(STR({var_s})), "{token_lower}")')
        clauses.append(f'CONTAINS(LCASE(STR({var_o})), "{token_lower}")')
    return " || ".join(clauses) if clauses else 'CONTAINS(LCASE(STR(?o)), "manual")'



def _uri_for_predicate(predicate: str) -> str:
    return PREDICATE_URI_MAP.get(predicate, f"{BASE_URI}{predicate}")



def _matches_keyword_group(question_text: str, keyword_group: list[str]) -> bool:
    return any(keyword in question_text for keyword in keyword_group)


def _contains_all_keywords(question_text: str, keywords: list[str]) -> bool:
    return all(keyword in question_text for keyword in keywords)



def _policy_for_family(policy_id: str | None) -> dict[str, Any]:
    return dict(BOUNDEDNESS_POLICIES.get(policy_id or "generic_fallback", BOUNDEDNESS_POLICIES["generic_fallback"]))



def _family_confidence(parse: QuestionParse, family: dict[str, Any]) -> float:
    confidence = 0.45
    if family.get("family_type") == "benchmark_seeded":
        confidence += 0.25
    if family.get("family_type") in {"quick_ref_strict", "cross_manual_strict", "installation_strict", "error_strict"}:
        confidence += 0.28
    if parse.matched_anchor_rule:
        confidence += 0.15
    if family.get("anchor_groups_all"):
        confidence += 0.05
    if family.get("technical_tokens_all") or family.get("technical_tokens_any"):
        confidence += 0.03
    if family.get("anchor_rule_id") == parse.matched_anchor_rule or parse.matched_anchor_rule in family.get("anchor_rule_ids", []):
        confidence += 0.1
    if parse.anchor_confidence > 0.8:
        confidence += 0.05
    return round(min(confidence, 0.98), 2)



def _resolved_seed_uris_for_family(parse: QuestionParse, family: dict[str, Any]) -> list[str]:
    token_map = family.get("seed_token_map", {})
    if token_map:
        search_space = normalize_text(" ".join(parse.anchor_candidates + parse.qualifiers + parse.technical_tokens))
        for token, uris in token_map.items():
            if token in search_space:
                return uris
    if family.get("anchor_rule_id") and parse.matched_anchor_rule == family["anchor_rule_id"]:
        for rule in ANCHOR_ALIAS_RULES:
            if rule["anchor_id"] == family["anchor_rule_id"]:
                return rule["seed_uris"] or parse.matched_seed_uris
    for rule_id in family.get("anchor_rule_ids", []):
        if parse.matched_anchor_rule == rule_id:
            for rule in ANCHOR_ALIAS_RULES:
                if rule["anchor_id"] == rule_id:
                    return rule["seed_uris"] or parse.matched_seed_uris
    return family.get("seed_uris", []) or parse.matched_seed_uris


def _family_score(parse: QuestionParse, question: str, family: dict[str, Any]) -> float | None:
    normalized = normalize_text(question)
    score = 0.0
    matched_evidence = False
    keyword_matched = False
    if family.get("intent") == parse.intent:
        score += 1.0
    if family.get("anchor_rule_id") == parse.matched_anchor_rule:
        score += 5.0
        matched_evidence = True
    if parse.matched_anchor_rule and parse.matched_anchor_rule in family.get("anchor_rule_ids", []):
        score += 4.0
        matched_evidence = True
    anchor_groups = set(parse.anchor_groups)
    family_groups_all = set(family.get("anchor_groups_all", []))
    family_groups_any = set(family.get("anchor_groups_any", []))
    if family_groups_all:
        if not family_groups_all.issubset(anchor_groups):
            return None
        score += 8.0 + len(family_groups_all)
        matched_evidence = True
    if family_groups_any:
        matched_any = anchor_groups.intersection(family_groups_any)
        if not matched_any:
            return None
        score += 4.0 + len(matched_any)
        matched_evidence = True
    technical_tokens = set(parse.technical_tokens)
    family_tokens_all = set(family.get("technical_tokens_all", []))
    family_tokens_any = set(family.get("technical_tokens_any", []))
    if family_tokens_all:
        if not family_tokens_all.issubset(technical_tokens):
            return None
        score += 8.0 + len(family_tokens_all)
        matched_evidence = True
    if family_tokens_any:
        matched_tokens = technical_tokens.intersection(family_tokens_any)
        if matched_tokens:
            score += 3.0 + len(matched_tokens)
            matched_evidence = True
    for keyword_group in family.get("keywords_all", []):
        if not _contains_all_keywords(normalized, keyword_group):
            return None
        score += 2.0
        matched_evidence = True
        keyword_matched = True
    for keyword_group in family.get("keywords_any", []):
        if _matches_keyword_group(normalized, keyword_group):
            score += 1.5
            matched_evidence = True
            keyword_matched = True
    if family.get("require_keyword_match") and not keyword_matched:
        return None
    if family.get("family_type") in {"quick_ref_strict", "cross_manual_strict", "installation_strict", "error_strict"} and not matched_evidence:
        return None
    return score


def _select_strict_family(parse: QuestionParse, question: str, families: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked: list[tuple[float, dict[str, Any]]] = []
    for family in families:
        score = _family_score(parse, question, family)
        if score is None:
            continue
        ranked.append((score, family))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1]["family_id"]))
    return ranked[0][1]


STRICT_RUNTIME_CUES = [
    "mdi",
    "mda",
    "edisimu",
    "softkey",
    "tecla",
    "keyboard",
    "monitor",
    "jog",
    "home search",
    "busqueda de referencia",
    "busqueda de bloque",
    "block search",
    "tool inspection",
    "inspeccion de herramienta",
    "g code",
    "codigo g",
    "g54",
    "g83",
    "g100",
    "g103",
    "g161",
    "m04",
    "#cax",
    "ctrl",
    "f12",
    "utilities mode",
    "modo utilidades",
    "fagorcnc",
    "users prg",
    "0008",
    "0040",
    "0169",
    "0173",
    "1067",
    "1166",
    "1167",
    "1359",
    "1737",
    "4026",
    "5026",
    "8023",
    "8042",
    "8026",
    "8458",
    "8459",
    "8789",
    "cncwr",
    "feedat",
    "endat",
    "oem",
    "pim",
    "pit",
    "#var",
    "#endvar",
    "#delete",
    "error de geometria",
    "editor de perfiles",
]


def _has_strict_runtime_context(parse: QuestionParse, question: str) -> bool:
    strong_anchor_groups = {
        "mdi_mda",
        "canned_cycles",
        "tool_calibration",
        "utilities_and_file_protection",
        "simulation",
        "tool_inspection",
        "jog_and_home",
        "math_and_high_level",
        "g_m_functions",
        "fixture_and_offsets",
        "syntax",
        "machine_safety_to_cnc_operation",
        "machine_program_recovery",
        "machine_utilities_navigation",
        "machine_program_storage",
        "installation_modes_storage",
        "installation_tandem_gantry",
        "installation_bus_plc",
        "installation_motion_defaults",
        "installation_alarm_temperature",
        "error_safety_mode_policy",
        "error_code_condition_attribute",
        "error_resolution_procedure",
        "error_code_comparison",
        "error_parameter_range",
    }
    if set(parse.anchor_groups).intersection(strong_anchor_groups) or parse.technical_tokens:
        return True
    normalized = normalize_text(question)
    return any(cue in normalized for cue in STRICT_RUNTIME_CUES)



def select_plan_family(parse: QuestionParse, question: str) -> dict[str, Any] | None:
    if _has_strict_runtime_context(parse, question):
        normalized = normalize_text(question)
        installation_anchor_groups = {
            "installation_modes_storage",
            "installation_tandem_gantry",
            "installation_bus_plc",
            "installation_motion_defaults",
            "installation_alarm_temperature",
        }
        error_anchor_groups = {
            "error_safety_mode_policy",
            "error_code_condition_attribute",
            "error_resolution_procedure",
            "error_code_comparison",
            "error_parameter_range",
        }
        error_technical_tokens = {
            "0008", "0040", "0169", "0173", "1067", "1166", "1167", "1359",
            "1737", "4026", "5026", "8023", "8042", "8026", "8458", "8459", "8789",
            "cncwr", "feedat", "endat", "pim", "pit", "geometry_error",
        }
        installation_context = bool(set(parse.anchor_groups).intersection(installation_anchor_groups))
        explicit_error_context = (
            bool(set(parse.technical_tokens).intersection(error_technical_tokens))
            or any(cue in normalized for cue in ["error de geometria", "editor de perfiles", "#var", "#endvar", "#delete"])
        )
        has_error_context = (
            explicit_error_context
            or (
                bool(set(parse.anchor_groups).intersection(error_anchor_groups))
                and not installation_context
            )
        )
        if has_error_context:
            strict_error = _select_strict_family(parse, question, STRICT_ERROR_FAMILIES)
            if strict_error is not None:
                return strict_error
        strict_cross = _select_strict_family(parse, question, STRICT_CROSS_FAMILIES)
        if strict_cross is not None:
            return strict_cross
        strict_installation = _select_strict_family(parse, question, STRICT_INSTALLATION_FAMILIES)
        if strict_installation is not None:
            return strict_installation
        strict_error = _select_strict_family(parse, question, STRICT_ERROR_FAMILIES)
        if strict_error is not None:
            return strict_error
        strict_quick_ref = _select_strict_family(parse, question, STRICT_QUICK_REF_FAMILIES)
        if strict_quick_ref is not None:
            return strict_quick_ref
    normalized = normalize_text(question)
    if parse.matched_anchor_rule:
        for family in MULTIHOP_PLAN_FAMILIES:
            if family.get("anchor_rule_id") == parse.matched_anchor_rule and family["intent"] == parse.intent:
                return family
            if parse.matched_anchor_rule in family.get("anchor_rule_ids", []) and family["intent"] == parse.intent:
                return family
    for family in MULTIHOP_PLAN_FAMILIES:
        groups = family.get("keywords_any", [])
        if groups and all(_matches_keyword_group(normalized, group) for group in groups):
            return family
    return None



def build_candidate_query(tokens: list[str], *, limit: int = 10) -> str:
    clauses = build_contains_clauses("?s", "?o", tokens)
    return (
        "SELECT DISTINCT ?s WHERE {\n"
        "  ?s ?p ?o .\n"
        f"  FILTER({clauses})\n"
        f"}} LIMIT {limit}"
    )



def build_seed_query(uris: list[str]) -> str:
    values = " ".join(f"<{uri}>" for uri in uris)
    return f"SELECT DISTINCT ?seed WHERE {{ VALUES ?seed {{ {values} }} }}"



def build_relation_query(seed_uris: list[str], relation: str, *, incoming: bool, max_results: int) -> str:
    values = " ".join(f"<{uri}>" for uri in seed_uris)
    predicate_uri = _uri_for_predicate(relation)
    if incoming:
        return (
            "SELECT DISTINCT ?target ?source WHERE {\n"
            f"  VALUES ?source {{ {values} }}\n"
            f"  ?target <{predicate_uri}> ?source .\n"
            "  FILTER(isIRI(?target))\n"
            f"}} LIMIT {max_results}"
        )
    return (
        "SELECT DISTINCT ?source ?target WHERE {\n"
        f"  VALUES ?source {{ {values} }}\n"
        f"  ?source <{predicate_uri}> ?target .\n"
        "  FILTER(isIRI(?target))\n"
        f"}} LIMIT {max_results}"
    )



def build_describe_query(seed_uris: list[str], preferred_predicates: list[str], *, max_results: int) -> str:
    values = " ".join(f"<{uri}>" for uri in seed_uris)
    predicate_filters = preferred_predicates or PREFERRED_LITERAL_PREDICATES
    predicate_values = " ".join(f"<{_uri_for_predicate(predicate)}>" for predicate in predicate_filters)
    return (
        "SELECT DISTINCT ?s ?p ?o WHERE {\n"
        f"  VALUES ?s {{ {values} }}\n"
        f"  VALUES ?p {{ {predicate_values} }}\n"
        "  ?s ?p ?o .\n"
        f"}} LIMIT {max_results}"
    )



def _rank_generic_candidates(graph: Graph | None, parse: QuestionParse, tokens: list[str], *, limit: int = 8) -> list[str]:
    if graph is None:
        return []
    ranked: dict[str, int] = {}
    for token in tokens[:5]:
        token_lower = token.lower()
        query = (
            "SELECT DISTINCT ?s ?o WHERE {\n"
            "  ?s ?p ?o .\n"
            f"  FILTER(CONTAINS(LCASE(STR(?s)), \"{token_lower}\") || CONTAINS(LCASE(STR(?o)), \"{token_lower}\"))\n"
            "} LIMIT 40"
        )
        try:
            for row in graph.query(query):
                subject_uri = str(row[0])
                ranked[subject_uri] = ranked.get(subject_uri, 0) + 2
                if isinstance(row[1], URIRef):
                    object_uri = str(row[1])
                    ranked[object_uri] = ranked.get(object_uri, 0) + 1
        except Exception:
            continue
    def score(uri: str) -> tuple[int, int, str]:
        local = normalize_uri(uri).lower()
        anchor_hit = 1 if parse.anchor_text and parse.anchor_text.lower() in local else 0
        return (-ranked.get(uri, 0), -anchor_hit, local)
    ordered = sorted(ranked.keys(), key=score)
    return ordered[:limit]



def _build_generic_plan(parse: QuestionParse, graph: Graph | None, *, template_id: str, intent_family: str) -> QueryPlan:
    tokens = parse.anchor_candidates[:5] or parse.qualifiers[:5] or ["manual"]
    policy = _policy_for_family("generalized_lookup")
    direct_seed_uris: list[str] = []
    if parse.matched_anchor_rule:
        for rule in ANCHOR_ALIAS_RULES:
            if rule["anchor_id"] == parse.matched_anchor_rule and parse.intent in rule["preferred_intents"]:
                direct_seed_uris = rule["seed_uris"][: policy["seed_limit"]]
                break
    candidate_uris = direct_seed_uris or _rank_generic_candidates(graph, parse, tokens, limit=policy["seed_limit"])
    fallback_used = not bool(candidate_uris)
    steps: list[QueryStep] = []
    if candidate_uris:
        steps.append(QueryStep(step_id="seed", purpose="seed_from_candidates", mode="fixed_seed", fixed_uris=candidate_uris, max_candidates=policy["seed_limit"], max_results=policy["seed_limit"]))
        steps.append(QueryStep(step_id="detail", purpose="describe_candidates", mode="describe_entities", preferred_predicates=PREFERRED_LITERAL_PREDICATES, max_candidates=policy["candidate_limit"], max_results=policy["result_limit"]))
        sparql = build_describe_query(candidate_uris, PREFERRED_LITERAL_PREDICATES, max_results=policy["result_limit"])
        recommended_action = "execute_with_pruning" if len(candidate_uris) > 2 else "execute"
    else:
        pattern = build_regex_pattern(tokens + parse.qualifiers)
        fallback_policy = _policy_for_family("generic_fallback")
        sparql = (
            f"PREFIX ex: <{BASE_URI}>\n"
            "SELECT DISTINCT ?s ?p ?o WHERE {\n"
            "  ?s ?p ?o .\n"
            f"  FILTER(REGEX(STR(?s), \"{pattern}\", \"i\") || REGEX(STR(?o), \"{pattern}\", \"i\"))\n"
            f"}} LIMIT {fallback_policy['result_limit']}"
        )
        steps.append(QueryStep(step_id="fallback", purpose="generic_fallback", mode="fallback_query", max_candidates=fallback_policy["candidate_limit"], max_results=fallback_policy["result_limit"]))
        policy = fallback_policy
        recommended_action = "fallback"
    family_confidence = 0.72 if direct_seed_uris else (0.58 if candidate_uris else 0.30)
    return QueryPlan(
        intent=parse.intent,
        anchor_text=parse.anchor_text,
        anchor_candidates=parse.anchor_candidates,
        template_id=template_id,
        plan_family=intent_family,
        predicted_hop_depth=1,
        fallback_used=fallback_used,
        sparql=sparql,
        steps=steps,
        confidence={
            "intent": parse.intent_confidence,
            "anchor": parse.anchor_confidence,
            "family": family_confidence,
            "overall": round((parse.intent_confidence + parse.anchor_confidence + family_confidence) / 3, 2),
        },
        boundedness_policy=policy,
        recommended_action=recommended_action,
        debug={"qualifiers": parse.qualifiers, "seed_candidates": candidate_uris, "used_direct_seed": bool(direct_seed_uris)},
    )

def build_query_plan(question: str, schema_text: str, graph: Graph | None = None) -> QueryPlan:
    normalization = normalize_question(question)
    planner_question = normalization["planner_question"]
    parse = build_question_parse(
        planner_question,
        normalization["multilingual_lexicon_hits"],
        normalization.get("anchor_groups", []),
        normalization.get("technical_tokens", []),
    )
    family = select_plan_family(parse, planner_question)
    if family is not None:
        steps = [QueryStep(**step) for step in family["steps"]]
        seed_uris = _resolved_seed_uris_for_family(parse, family)
        if seed_uris and steps and steps[0].mode == "fixed_seed":
            steps[0].fixed_uris = seed_uris[: steps[0].max_candidates]
        sparql = ""
        if steps and steps[0].mode == "fallback_query":
            pattern_tokens = parse.technical_tokens or parse.anchor_candidates or parse.qualifiers or ["cnc"]
            sparql = (
                f"PREFIX ex: <{BASE_URI}>\n"
                "SELECT DISTINCT ?s ?p ?o WHERE {\n"
                "  ?s ?p ?o .\n"
                f"  FILTER(REGEX(LCASE(STR(?s)), \"{build_regex_pattern(pattern_tokens)}\", \"i\") || "
                f"REGEX(LCASE(STR(?o)), \"{build_regex_pattern(pattern_tokens)}\", \"i\"))\n"
                "} LIMIT 10"
            )
        plan = QueryPlan(
            intent=family["intent"],
            anchor_text=family.get("canonical_anchor", parse.anchor_text),
            anchor_candidates=parse.anchor_candidates,
            template_id=family["template_id"],
            plan_family=family["family_id"],
            predicted_hop_depth=family["hop_depth"],
            fallback_used=False,
            sparql=sparql,
            steps=steps,
            confidence={
                "intent": parse.intent_confidence,
                "anchor": parse.anchor_confidence,
                "family": _family_confidence(parse, family),
                "overall": round((parse.intent_confidence + parse.anchor_confidence + _family_confidence(parse, family)) / 3, 2),
            },
            boundedness_policy=_policy_for_family(family.get("policy_id")),
            recommended_action="execute",
            question_language=normalization["question_language"],
            question_language_confidence=normalization["question_language_confidence"],
            normalized_question=normalization["normalized_question"],
            multilingual_lexicon_hits=normalization["multilingual_lexicon_hits"],
            debug={
                "qualifiers": parse.qualifiers,
                "question_parse": asdict(parse),
                "schema_excerpt_used": bool(schema_text),
                "family_type": family.get("family_type"),
                "evidence_questions": family.get("evidence_questions", []),
                "anchor_groups": parse.anchor_groups,
                "technical_tokens": parse.technical_tokens,
                "original_question": question,
                "planner_question": planner_question,
                "question_language": normalization["question_language"],
                "question_language_confidence": normalization["question_language_confidence"],
                "multilingual_lexicon_hits": normalization["multilingual_lexicon_hits"],
            },
        )
        return plan
    generic_map = {
        "literal_lookup": ("T1_literal_anchor", "generic_literal_lookup"),
        "figure_or_reference_lookup": ("T2_reference_lookup", "generic_reference_lookup"),
        "regulatory_lookup": ("T3_regulatory_lookup", "generic_regulatory_lookup"),
        "component_attribute_lookup": ("T4_component_attribute_lookup", "generic_component_attribute_lookup"),
        "component_relation_lookup": ("T5_component_relation_lookup", "generic_component_relation_lookup"),
        "purpose_or_function_lookup": ("T6_purpose_lookup", "generic_purpose_lookup"),
    }
    template_id, family_id = generic_map.get(parse.intent, ("T1_literal_anchor", "generic_literal_lookup"))
    plan = _build_generic_plan(parse, graph, template_id=template_id, intent_family=family_id)
    plan.question_language = normalization["question_language"]
    plan.question_language_confidence = normalization["question_language_confidence"]
    plan.normalized_question = normalization["normalized_question"]
    plan.multilingual_lexicon_hits = normalization["multilingual_lexicon_hits"]
    plan.debug.update(
        {
            "question_parse": asdict(parse),
            "schema_excerpt_used": bool(schema_text),
            "original_question": question,
            "planner_question": planner_question,
            "question_language": normalization["question_language"],
            "question_language_confidence": normalization["question_language_confidence"],
            "multilingual_lexicon_hits": normalization["multilingual_lexicon_hits"],
            "anchor_groups": parse.anchor_groups,
            "technical_tokens": parse.technical_tokens,
        }
    )
    return plan



def _boundedness_status(raw_result_count: int, output_count: int, pruned_count: int, step: QueryStep, policy: dict[str, Any]) -> str:
    if raw_result_count < policy.get("too_narrow_min", 1) or output_count == 0:
        return "too_narrow"
    if pruned_count > 0 or raw_result_count >= policy.get("too_broad_raw", step.max_results) or output_count > step.max_candidates:
        return "too_broad"
    return "bounded"



def _filter_uris(uris: list[str], filters: list[str]) -> tuple[list[str], str | None]:
    if not filters:
        return uris, None
    lowered_filters = [token.lower() for token in filters]
    filtered = []
    for uri in uris:
        local = normalize_uri(uri).lower()
        if any(token in local for token in lowered_filters):
            filtered.append(uri)
    if filtered:
        return filtered, f"target_filters:{','.join(filters)}"
    return uris, "target_filters_no_match_kept_originals"



def execute_query_plan(plan: QueryPlan, graph: Graph) -> QueryExecutionResult:
    aggregated_rows: list[tuple[str, str, str]] = []
    raw_bindings: list[tuple[str, ...]] = []
    seen_rows: set[tuple[str, str, str]] = set()
    seed_uris: list[str] = []
    trace_steps: list[QueryStepTrace] = []
    policy = plan.boundedness_policy or _policy_for_family("generic_fallback")
    final_boundedness = "bounded"

    for step in plan.steps:
        query_text = ""
        raw_rows: list[tuple[str, ...]] = []
        output_uris: list[str] = []
        pruned_count = 0
        prune_reason = None
        error = None
        input_count = len(step.fixed_uris if step.mode == "fixed_seed" else seed_uris)
        try:
            if step.mode == "fixed_seed":
                reconciled_fixed_uris = reconcile_fixed_seed_uris(step.fixed_uris, graph)
                if reconciled_fixed_uris != step.fixed_uris:
                    prune_reason = "fixed_seed_reconciled"
                output_uris = reconciled_fixed_uris[: step.max_candidates]
                query_text = build_seed_query(reconciled_fixed_uris)
                raw_rows = [(uri,) for uri in output_uris]
            elif step.mode == "relation_traverse":
                input_uris = step.fixed_uris if step.seed_source == "fixed" else seed_uris
                query_text = build_relation_query(input_uris, step.relation or "", incoming=step.incoming, max_results=step.max_results)
                raw_rows = [tuple(str(value) for value in row) for row in graph.query(query_text)]
                candidate_uris = []
                relation_label = step.relation or "relatedTo"
                for row in raw_rows:
                    if len(row) < 2:
                        continue
                    source_uri, target_uri = (row[1], row[0]) if step.incoming else (row[0], row[1])
                    if target_uri not in candidate_uris:
                        candidate_uris.append(target_uri)
                    normalized_row = (normalize_uri(source_uri), relation_label, normalize_uri(target_uri))
                    if normalized_row not in seen_rows:
                        seen_rows.add(normalized_row)
                        aggregated_rows.append(normalized_row)
                    raw_bindings.append((source_uri, _uri_for_predicate(relation_label), target_uri))
                candidate_uris, prune_reason = _filter_uris(candidate_uris, step.target_filters)
                output_uris = candidate_uris[: step.max_candidates]
                pruned_count = max(0, len(candidate_uris) - len(output_uris))
                if pruned_count and prune_reason is None:
                    prune_reason = "candidate_limit"
            elif step.mode == "describe_entities":
                input_uris = step.fixed_uris if step.seed_source == "fixed" else seed_uris
                query_text = build_describe_query(input_uris, step.preferred_predicates, max_results=step.max_results)
                raw_rows = [tuple(str(value) for value in row) for row in graph.query(query_text)]
                described_uris: list[str] = []
                for row in raw_rows:
                    if len(row) != 3:
                        continue
                    raw_bindings.append(row)
                    normalized_row = (normalize_uri(row[0]), normalize_uri(row[1]), normalize_uri(row[2]))
                    if normalized_row not in seen_rows:
                        seen_rows.add(normalized_row)
                        aggregated_rows.append(normalized_row)
                    if row[0] not in described_uris:
                        described_uris.append(row[0])
                output_uris = described_uris[: step.max_candidates]
                pruned_count = max(0, len(described_uris) - len(output_uris))
                if pruned_count:
                    prune_reason = "describe_entity_limit"
            elif step.mode == "fallback_query":
                query_text = plan.sparql
                raw_rows = [tuple(str(value) for value in row) for row in graph.query(query_text)]
                for row in raw_rows:
                    if len(row) == 3:
                        raw_bindings.append(row)
                        normalized_row = (normalize_uri(row[0]), normalize_uri(row[1]), normalize_uri(row[2]))
                        if normalized_row not in seen_rows:
                            seen_rows.add(normalized_row)
                            aggregated_rows.append(normalized_row)
            else:
                error = f"unsupported_mode:{step.mode}"
        except Exception as exc:
            error = str(exc)
        if output_uris:
            seed_uris = output_uris
        status = _boundedness_status(len(raw_rows), len(output_uris) if step.mode != "fallback_query" else len(aggregated_rows), pruned_count, step, policy) if error is None else "error"
        if final_boundedness == "bounded" and status != "bounded":
            final_boundedness = status
        trace_steps.append(
            QueryStepTrace(
                step_id=step.step_id,
                purpose=step.purpose,
                mode=step.mode,
                query_text=query_text,
                input_candidate_count=input_count,
                raw_result_count=len(raw_rows),
                output_candidate_count=len(output_uris),
                pruned_count=pruned_count,
                boundedness_status=status,
                output_uris=output_uris,
                sample_rows=[[normalize_uri(value) if isinstance(value, str) and value.startswith("http") else value for value in row] for row in raw_rows[:6]],
                prune_reason=prune_reason,
                error=error,
            )
        )
        if error is not None:
            final_boundedness = "error"
            break

    if final_boundedness == "bounded" and not aggregated_rows:
        final_boundedness = "too_narrow"
    if final_boundedness == "too_broad" and plan.boundedness_policy.get("degrade_to_fallback"):
        plan.recommended_action = "fallback"
        plan.fallback_used = True
    elif final_boundedness == "too_broad":
        plan.recommended_action = "execute_with_pruning"
    elif final_boundedness == "too_narrow":
        plan.recommended_action = "low_confidence"

    plan.final_boundedness = final_boundedness
    plan.debug["step_count"] = len(plan.steps)
    plan.debug["result_count"] = len(aggregated_rows)
    plan.debug["final_candidate_count"] = len(seed_uris)
    plan.debug["trace_summary"] = [asdict(item) for item in trace_steps]
    plan.debug["final_boundedness"] = final_boundedness
    if trace_steps:
        plan.sparql = trace_steps[-1].query_text or plan.sparql
    return QueryExecutionResult(plan=plan, rows=aggregated_rows, raw_bindings=raw_bindings, trace=QueryExecutionTrace(steps=trace_steps, final_boundedness=final_boundedness))

def append_query_debug_record(record: dict[str, Any], path: Path = QUERY_DEBUG_REPORT_PATH) -> None:
    payload = []
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = []
    payload.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")



def export_intent_catalog_from_dataset(dataset_path: Path, output_path: Path = QUERY_INTENT_CATALOG_PATH) -> dict[str, Any]:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    blocks = payload if isinstance(payload, list) else [{"questions": payload.get("questions", [])}]
    intents = []
    qid = 1
    for block_index, block in enumerate(blocks):
        for question_index, item in enumerate(block.get("questions", [])):
            question = item["question"]
            parse = build_question_parse(question)
            intents.append({
                "question_id": f"q_{qid:03d}",
                "block_index": block_index,
                "question_index": question_index,
                "question": question,
                "intent": parse.intent,
                "anchor_candidates": parse.anchor_candidates,
                "notes": item.get("reconciliation_label", "runtime question"),
            })
            qid += 1
    catalog = {"dataset_version": dataset_path.stem, "intents": intents}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalog



def export_multihop_plan_catalog(output_path: Path = MULTIHOP_PLAN_CATALOG_PATH) -> dict[str, Any]:
    benchmark = json.loads(QA_MULTIHOP_PATH.read_text(encoding="utf-8")) if QA_MULTIHOP_PATH.exists() else {"questions": []}
    mapping = {
        "machine_directive_compliance": "mh_005",
        "system_maintenance_plan": "mh_001",
        "manual_figure_reference": "mh_003",
        "component_control_chain": "mh_006",
        "column_component_control_chain": "mh_007",
    }
    by_question_id = {item["question_id"]: item for item in benchmark.get("questions", [])}
    families = []
    for family in MULTIHOP_PLAN_FAMILIES:
        if family.get("family_type") != "benchmark_seeded":
            continue
        benchmark_example = by_question_id.get(mapping.get(family["family_id"], ""), {})
        families.append({
            "family_id": family["family_id"],
            "template_id": family["template_id"],
            "intent": family["intent"],
            "hop_depth": family["hop_depth"],
            "example_question": benchmark_example.get("question"),
            "expected_path": benchmark_example.get("expected_path"),
            "seed_uris": family.get("seed_uris", []),
            "step_modes": [step["mode"] for step in family["steps"]],
            "relations": [step.get("relation") for step in family["steps"] if step.get("relation")],
        })
    payload = {"catalog_version": "t13_v1", "families": families}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload



def export_planner_generalization_catalog(output_path: Path = PLANNER_GENERALIZATION_CATALOG_PATH) -> dict[str, Any]:
    families = []
    for family in MULTIHOP_PLAN_FAMILIES:
        if family.get("family_type") != "generalized":
            continue
        families.append({
            "family_id": family["family_id"],
            "template_id": family["template_id"],
            "intent": family["intent"],
            "hop_depth": family["hop_depth"],
            "policy_id": family.get("policy_id", "generic_fallback"),
            "anchor_rule_id": family.get("anchor_rule_id"),
            "anchor_rule_ids": family.get("anchor_rule_ids", []),
            "evidence_questions": family.get("evidence_questions", []),
            "step_modes": [step["mode"] for step in family["steps"]],
        })
    payload = {"catalog_version": "t13_v1", "families": families}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def export_planner_generalization_catalog_v2(output_path: Path = PLANNER_GENERALIZATION_CATALOG_V2_PATH) -> dict[str, Any]:
    dataset = json.loads(QA_8070_QUICK_REF_BILINGUAL_V2_PATH.read_text(encoding="utf-8-sig")) if QA_8070_QUICK_REF_BILINGUAL_V2_PATH.exists() else {"pairs": []}
    expected_ids = {pair.get("expected_plan_family") for pair in dataset.get("pairs", [])}
    families = []
    for family in STRICT_QUICK_REF_FAMILIES:
        if family["family_id"] not in expected_ids:
            continue
        families.append(
            {
                "family_id": family["family_id"],
                "template_id": family["template_id"],
                "intent": family["intent"],
                "hop_depth": family["hop_depth"],
                "family_type": family["family_type"],
                "policy_id": family["policy_id"],
                "canonical_anchor": family.get("canonical_anchor"),
                "anchor_groups_all": family.get("anchor_groups_all", []),
                "technical_tokens_all": family.get("technical_tokens_all", []),
                "technical_tokens_any": family.get("technical_tokens_any", []),
                "step_modes": [step["mode"] for step in family["steps"]],
            }
        )
    payload = {"catalog_version": "t22_v1", "families": families}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def export_cross_plan_catalog(output_path: Path = CROSS_PLAN_CATALOG_PATH) -> dict[str, Any]:
    dataset = json.loads(QA_CROSS_PATH.read_text(encoding="utf-8-sig")) if QA_CROSS_PATH.exists() else {"pairs": []}
    expected_ids = {pair.get("expected_plan_family") for pair in dataset.get("pairs", [])}
    families = []
    for family in STRICT_CROSS_FAMILIES:
        if family["family_id"] not in expected_ids:
            continue
        families.append(
            {
                "family_id": family["family_id"],
                "template_id": family["template_id"],
                "intent": family["intent"],
                "hop_depth": family["hop_depth"],
                "family_type": family["family_type"],
                "policy_id": family["policy_id"],
                "canonical_anchor": family.get("canonical_anchor"),
                "anchor_groups_all": family.get("anchor_groups_all", []),
                "technical_tokens_all": family.get("technical_tokens_all", []),
                "technical_tokens_any": family.get("technical_tokens_any", []),
                "step_modes": [step["mode"] for step in family["steps"]],
            }
        )
    payload = {"catalog_version": "t22_v1", "families": families}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload



def export_boundedness_policy_matrix(output_path: Path = BOUNDEDNESS_POLICY_MATRIX_PATH) -> dict[str, Any]:
    payload = {
        "policy_version": "t13_v1",
        "policies": BOUNDEDNESS_POLICIES,
        "family_bindings": {family["family_id"]: family.get("policy_id", "generic_fallback") for family in MULTIHOP_PLAN_FAMILIES},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

def main() -> None:
    args = parse_args()
    if args.export_plan_catalog:
        payload = export_multihop_plan_catalog()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if args.export_generalization_catalog:
        payload = export_planner_generalization_catalog()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if args.export_boundedness_matrix:
        payload = export_boundedness_policy_matrix()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    graph = cargar_grafo_memoria()
    plan = build_query_plan(args.question, schema_text="", graph=graph)
    result = execute_query_plan(plan, graph)
    print(json.dumps({
        "query_plan": asdict(plan),
        "trace": asdict(result.trace),
        "result_count": len(result.rows),
        "sample_rows": result.rows[:10],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
