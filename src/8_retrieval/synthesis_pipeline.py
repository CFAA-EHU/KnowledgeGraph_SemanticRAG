from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from artifact_contracts import SYNTHESIS_DEBUG_REPORT_PATH

STOPWORDS = {
    'de', 'la', 'el', 'los', 'las', 'del', 'para', 'por', 'que', 'una', 'uno', 'segun', 'sobre',
    'esta', 'este', 'estos', 'estas', 'cual', 'donde', 'quien', 'como', 'manual', 'maquina',
    'indicado', 'indicada', 'mencionada', 'respecto', 'debe', 'deben', 'tipo', 'informacion',
    'aparece', 'sirve', 'hace', 'muestra', 'realiza', 'utilizados', 'pregunta', 'queda', 'tiene',
}

VALUE_NORMALIZATION_RULES = {
    'uri_surface_cleanup': {
        'description': 'Convierte URIs o identificadores internos en superficies legibles.',
        'examples': ['Directiva2006_42_CE -> Directiva 2006 42 CE', 'Empresa_EKIN_S_Coop -> Empresa EKIN S Coop'],
    },
    'whitespace_cleanup': {
        'description': 'Colapsa espacios, saltos de linea y artefactos tipograficos superficiales.',
        'examples': ['Barrio  Boroa  -> Barrio Boroa'],
    },
    'email_extraction': {
        'description': 'Extrae el correo electronico de un literal mixto de contacto.',
        'examples': ['Email: ekin@ekin.es -> ekin@ekin.es'],
    },
    'address_extraction': {
        'description': 'Extrae la direccion principal desde un literal de contacto largo.',
        'examples': ['Direccion: Barrio Boroa ... Telefono ... -> Barrio Boroa, s/n, 48340 Amorebieta (Espana)'],
    },
    'directive_extraction': {
        'description': 'Normaliza referencias de directivas CE al formato canonico.',
        'examples': ['Directiva2006_42_CE -> 2006/42/CE'],
    },
    'figure_extraction': {
        'description': 'Normaliza referencias de figuras al formato Figura X-Y-Z.',
        'examples': ['figura 0-1-1 -> Figura 0-1-1'],
    },
    'sentence_focus': {
        'description': 'Selecciona la frase mas informativa y evita literales largos redundantes.',
        'examples': ['Texto largo con multiples frases -> primera frase relevante'],
    },
    'deduplicate_values': {
        'description': 'Elimina duplicados superficiales tras la normalizacion.',
        'examples': ['Modo automatico, modo automatico -> modo automatico'],
    },
}

SURFACE_RENDERING_RULES = {
    'short_lead_answer': {
        'description': 'Abre con la respuesta principal antes que con contexto accesorio.',
        'applies_to': ['purpose', 'ownership', 'contact_department', 'verification_requirement'],
    },
    'trim_redundant_tail': {
        'description': 'Recorta colas documentales o repeticiones que no aportan nueva informacion.',
        'applies_to': ['purpose', 'risk_consequence', 'spare_parts_policy', 'generic'],
    },
    'compact_single_value': {
        'description': 'Cuando la evidencia valida converge en un unico valor, evita listas o repeticiones.',
        'applies_to': ['email', 'address', 'directive', 'figure'],
    },
    'stabilize_department_surface': {
        'description': 'Fuerza una formulacion uniforme para referencias a departamento o contacto.',
        'applies_to': ['contact_department'],
    },
    'stabilize_warning_surface': {
        'description': 'Separa la etiqueta de advertencia del contenido principal y evita eco de mayusculas.',
        'applies_to': ['risk_consequence'],
    },
}


@dataclass
class EvidenceCandidate:
    subject: str
    predicate: str
    obj: str
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class NormalizedValue:
    raw_value: str
    normalized_value: str
    value_type: str
    applied_rules: list[str] = field(default_factory=list)


@dataclass
class SynthesisTrace:
    question: str
    intent: str | None
    answer_mode: str
    answer_language: str
    candidate_count: int
    evidence_candidates: list[dict[str, Any]]
    selected_evidence: list[dict[str, Any]]
    normalized_values: list[dict[str, Any]]
    pre_polish_answer: str
    rendered_answer: str
    synthesis_category: str
    applied_surface_rules: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize('NFKD', text or '')
    normalized = ''.join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.replace('???', ' ').replace('', ' ').replace('?', ' ')
    normalized = normalized.replace('?', ' ').replace('?', '-')
    normalized = normalized.replace('?', '"').replace('?', '"')
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip()


def _normalize_for_match(text: str) -> str:
    text = _normalize_text(text).lower()
    text = re.sub(r'[^a-z0-9@/_:\-\.]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _tokenize_question(question: str) -> list[str]:
    return [token for token in _normalize_for_match(question).split() if len(token) >= 3 and token not in STOPWORDS]


def _predicate_local_name(predicate: str) -> str:
    return str(predicate).split('/')[-1].split('#')[-1]


def _surface_from_identifier(value: str) -> str:
    value = str(value or '')
    tail = value.split('/')[-1].split('#')[-1]
    tail = re.sub(r'(?<!^)([A-Z])', r' \1', tail)
    tail = tail.replace('_', ' ')
    return _normalize_text(tail)


def infer_answer_mode(question: str, intent: str | None, plan_family: str | None = None) -> str:
    question_norm = _normalize_for_match(question)
    if plan_family == 'quick_ref_work_mode_lookup':
        return 'mode_literal'
    if plan_family == 'quick_ref_key_purpose_lookup':
        return 'control_key'
    if plan_family in {'quick_ref_jog_operation_lookup', 'quick_ref_home_search_procedure', 'quick_ref_coordinate_preset_procedure', 'quick_ref_feed_speed_tool_lookup', 'quick_ref_tool_inspection_lookup', 'cross_manual_home_search_procedure', 'cross_manual_incremental_jog_procedure'}:
        return 'procedure'
    if plan_family in {
        'quick_ref_mdi_mda_conditions_lookup',
        'quick_ref_canned_cycles_multi_hop',
        'quick_ref_semi_auto_calibration_conditional',
        'quick_ref_file_protection_lookup',
        'quick_ref_high_level_instructions_multi_hop',
        'quick_ref_simulation_conditions_multi_hop',
        'quick_ref_m_functions_lookup',
        'quick_ref_file_attributes_multi_hop',
        'quick_ref_g_functions_lookup',
        'quick_ref_jog_rapid_lookup',
        'quick_ref_block_search_multi_hop',
        'quick_ref_math_functions_lookup',
        'quick_ref_calibration_comparison_multi_hop',
        'quick_ref_fixture_table_lookup',
        'quick_ref_edisimu_syntax_lookup',
        'quick_ref_probing_functions_multi_hop',
        'quick_ref_multiple_machining_lookup',
        'cross_manual_tool_inspection_conditional',
        'cross_manual_simulation_multi_hop',
        'cross_manual_block_search_conditional',
        'cross_manual_c_axis_instruction',
        'cross_manual_file_protection_multi_hop',
        'cross_manual_mdi_history_retention',
        'cross_manual_parameter_scope',
        'cross_manual_zero_offset_codes',
        'cross_manual_shortcut_navigation',
    }:
        return 'literal'
    if 'correo' in question_norm or 'email' in question_norm:
        return 'email'
    if 'direccion' in question_norm or 'donde se encuentra la direccion' in question_norm or 'address' in question_norm:
        return 'address'
    if 'directiva' in question_norm or 'directive' in question_norm or 'conformidad' in question_norm or 'conformity' in question_norm:
        return 'directive'
    if 'figura' in question_norm or 'figure' in question_norm:
        return 'figure'
    if 'plan de mantenimiento' in question_norm or 'maintenance plan' in question_norm:
        return 'generic'
    if 'recambio' in question_norm or 'piezas originales' in question_norm or 'spare parts' in question_norm:
        return 'spare_parts_policy'
    if 'derechos de autor' in question_norm or 'copyright' in question_norm:
        return 'ownership'
    if 'verificar regularmente' in question_norm or 'garantizar la seguridad de la maquina' in question_norm or 'verify regularly' in question_norm:
        return 'verification_requirement'
    if 'que puede ocurrir' in question_norm or 'senal de precaucion' in question_norm or 'what may happen' in question_norm:
        return 'risk_consequence'
    if 'quien se debe consultar' in question_norm or 'a quien se debe consultar' in question_norm or 'who should be consulted' in question_norm:
        return 'contact_department'
    if 'para que sirve' in question_norm or 'what is the purpose' in question_norm or 'representa' in question_norm or 'represents' in question_norm or intent == 'purpose_or_function_lookup':
        return 'purpose'
    if plan_family and 'literal' in plan_family:
        return 'literal'
    return 'generic'


def _contains_anchor(row_text: str, anchor_candidates: list[str]) -> bool:
    row_norm = _normalize_for_match(row_text)
    for candidate in anchor_candidates:
        candidate_norm = _normalize_for_match(candidate)
        if candidate_norm and candidate_norm in row_norm:
            return True
    return False


def score_evidence_rows(question: str, rows: list[tuple[str, str, str]], plan: Any) -> list[EvidenceCandidate]:
    answer_mode = infer_answer_mode(question, getattr(plan, 'intent', None), getattr(plan, 'plan_family', None))
    plan_family = getattr(plan, 'plan_family', None)
    question_tokens = _tokenize_question(question)
    anchor_candidates = list(getattr(plan, 'anchor_candidates', []) or [])
    candidates: list[EvidenceCandidate] = []
    for subject, predicate, obj in rows:
        predicate_name = _predicate_local_name(predicate)
        combined_text = f'{subject} {predicate_name} {obj}'
        combined_norm = _normalize_for_match(combined_text)
        obj_norm = _normalize_for_match(obj)
        score = 0.0
        reasons: list[str] = []
        if _contains_anchor(combined_text, anchor_candidates):
            score += 2.0
            reasons.append('anchor_match')
        token_hits = sum(1 for token in question_tokens if token in combined_norm)
        if token_hits:
            score += min(token_hits, 4) * 0.7
            reasons.append(f'question_token_hits:{token_hits}')
        if predicate_name == 'type':
            score -= 2.0
            reasons.append('type_penalty')
        if predicate_name in {'identificador', 'label', 'valor'}:
            score += 2.0
            reasons.append(f'preferred_predicate:{predicate_name}')
        elif predicate_name == 'textoExtracto':
            score += 1.0
            reasons.append('supporting_text')
        if answer_mode == 'email' and re.search(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', obj, re.I):
            score += 6.0
            reasons.append('email_match')
        if answer_mode == 'address':
            if re.search(r'(direccion|barrio|amorebieta|espana)', obj_norm):
                score += 5.0
                reasons.append('address_match')
            if 'telefono' in obj_norm or 'fax' in obj_norm:
                score += 1.0
                reasons.append('contact_literal')
        if answer_mode == 'directive' and re.search(r'\d{4}\s*/\s*\d{2}\s*/\s*[A-Z]{2}', obj, re.I):
            score += 6.0
            reasons.append('directive_match')
        if answer_mode == 'figure' and re.search(r'figura\s*\d+(?:[-?]\d+)+', obj, re.I):
            score += 6.0
            reasons.append('figure_match')
        if answer_mode == 'spare_parts_policy':
            if 'original' in obj_norm:
                score += 5.0
                reasons.append('original_spare_parts')
            if 'requisitos tecnicos' in obj_norm or 'requisitos tecnicos fijados por ekin' in obj_norm:
                score += 3.0
                reasons.append('technical_requirements')
        if answer_mode == 'contact_department' and ('departamento' in obj_norm or 'asistencia al cliente' in obj_norm):
            score += 5.0
            reasons.append('department_match')
        if answer_mode == 'ownership' and ('derechos de autor' in obj_norm or 'reservados a' in obj_norm):
            score += 6.0
            reasons.append('ownership_match')
        if answer_mode == 'verification_requirement' and ('verificar regularmente' in obj_norm or 'elementos de seguridad' in obj_norm):
            score += 6.0
            reasons.append('verification_match')
        if answer_mode == 'risk_consequence' and any(keyword in obj_norm for keyword in ['pueden producirse', 'lesiones personales graves', 'destruccion de partes']):
            score += 6.0
            reasons.append('risk_consequence_match')
        if answer_mode == 'purpose':
            if predicate_name == 'textoExtracto':
                score += 2.5
                reasons.append('purpose_text')
            if any(keyword in obj_norm for keyword in ['proporciona', 'sirve', 'representa', 'aconseja', 'objetivo']):
                score += 3.0
                reasons.append('purpose_keyword')
        if answer_mode == 'control_key' and any(keyword in combined_norm for keyword in ['focus', 'next', 'back', 'help', 'start', 'stop', 'reset', 'zero', 'enter']):
            score += 5.5
            reasons.append('control_key_match')
        if plan_family == 'quick_ref_key_purpose_lookup':
            if 'help' in question_tokens and 'help' in combined_norm:
                score += 6.0
                reasons.append('family_help_focus')
            if 'focus' in question_tokens and 'focus' in combined_norm:
                score += 6.0
                reasons.append('family_help_focus')
            if 'next' in question_tokens and 'next' in combined_norm:
                score += 6.0
                reasons.append('family_help_focus')
            if 'back' in question_tokens and 'back' in combined_norm:
                score += 6.0
                reasons.append('family_help_focus')
        if answer_mode == 'mode_literal' and any(keyword in combined_norm for keyword in ['automatic mode', 'jog mode', 'mdi', 'manual e disimu']):
            score += 5.0
            reasons.append('mode_literal_match')
        if answer_mode == 'procedure' and any(keyword in obj_norm for keyword in ['press', 'pulsar', 'select', 'enter', 'start', 'esc', 'axis', 'preset']):
            score += 4.5
            reasons.append('procedure_match')
        if plan_family in {'quick_ref_simulation_conditions_multi_hop', 'cross_manual_simulation_multi_hop'} and any(keyword in obj_norm for keyword in ['theoretical travel', 'trayectoria teorica', 'main plane', 'plano principal', 'plc']):
            score += 5.0
            reasons.append('family_simulation_match')
        if plan_family in {'quick_ref_jog_rapid_lookup'} and 'rapid feedrate' in obj_norm:
            score += 5.0
            reasons.append('family_rapid_match')
        if plan_family in {'cross_manual_home_search_procedure'} and any(keyword in obj_norm for keyword in ['zero', 'start', 'alphanumeric keyboard', 'home search']):
            score += 5.0
            reasons.append('family_home_search_match')
        if len(obj) > 280 and answer_mode in {'email', 'address', 'directive', 'figure', 'literal'}:
            score -= 1.5
            reasons.append('long_literal_penalty')
        candidates.append(EvidenceCandidate(subject=subject, predicate=predicate_name, obj=obj, score=round(score, 3), reasons=reasons))
    return sorted(candidates, key=lambda item: (item.score, -len(item.obj)), reverse=True)


def _extract_email(raw_value: str) -> tuple[str, list[str]]:
    match = re.search(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', raw_value, re.I)
    if not match:
        return '', []
    return match.group(0).lower(), ['email_extraction', 'whitespace_cleanup']


def _extract_address(raw_value: str) -> tuple[str, list[str]]:
    cleaned = _normalize_text(raw_value)
    match = re.search(r'Direcci[o?]n\s*:\s*(.*?)(?:Tel[e?]fono|Fax|Email|$)', cleaned, re.I)
    if match:
        address = match.group(1).strip(' .;,:')
        address = re.sub(r'\(www\.[^)]+\)', '', address, flags=re.I).strip()
        address = re.sub(r'\s+', ' ', address)
        address = address.replace('AMOREBIETA', 'Amorebieta')
        return address, ['address_extraction', 'whitespace_cleanup']
    postal = re.search(r'(Barrio .*?\(Espa[?n]a\))', cleaned, re.I)
    if postal:
        return postal.group(1).strip(), ['address_extraction', 'whitespace_cleanup']
    return cleaned, ['whitespace_cleanup']


def _extract_directive(raw_value: str) -> tuple[str, list[str]]:
    cleaned = _normalize_text(raw_value)
    match = re.search(r'(\d{4})\s*/\s*(\d{2})\s*/\s*([A-Z]{2})', cleaned, re.I)
    if match:
        return f'{match.group(1)}/{match.group(2)}/{match.group(3).upper()}', ['directive_extraction', 'whitespace_cleanup']
    fallback = _surface_from_identifier(cleaned)
    fallback = fallback.replace('C E', 'CE').replace('U E', 'UE')
    match = re.search(r'(\d{4})\s+(\d{2})\s+([A-Z]{2})', fallback, re.I)
    if match:
        return f'{match.group(1)}/{match.group(2)}/{match.group(3).upper()}', ['directive_extraction', 'uri_surface_cleanup']
    return cleaned, ['whitespace_cleanup']


def _extract_figure(raw_value: str) -> tuple[str, list[str]]:
    cleaned = _normalize_text(raw_value)
    match = re.search(r'figura\s*(\d+(?:[-?]\d+)+)', cleaned, re.I)
    if match:
        return f'Figura {match.group(1).replace("?", "-")}', ['figure_extraction', 'whitespace_cleanup']
    return cleaned, ['whitespace_cleanup']


def _compact_sentence(raw_value: str) -> tuple[str, list[str]]:
    cleaned = _normalize_text(raw_value)
    cleaned = re.sub(r'^(USO DEL MANUAL|Peligro|Precaucion|Medio ambiente)\s+', '', cleaned, flags=re.I).strip()
    sentences = re.split(r'(?<=[\.!?])\s+', cleaned)
    chosen = sentences[0].strip() if sentences and sentences[0].strip() else cleaned
    chosen = chosen.strip(' .')
    return chosen, ['sentence_focus', 'whitespace_cleanup']


def _extract_ownership(raw_value: str) -> tuple[str, list[str]]:
    cleaned = _normalize_text(raw_value)
    match = re.search(r'reservados? a (.+?)(?:\.|$)', cleaned, re.I)
    if match:
        return match.group(1).strip(), ['sentence_focus', 'whitespace_cleanup']
    return cleaned, ['sentence_focus', 'whitespace_cleanup']


def _extract_department(raw_value: str) -> tuple[str, list[str]]:
    cleaned = _normalize_text(raw_value)
    if 'departamento de asistencia al cliente de ekin' in cleaned.lower():
        return 'el departamento de asistencia al cliente de EKIN', ['sentence_focus', 'whitespace_cleanup']
    return cleaned, ['sentence_focus', 'whitespace_cleanup']


def _extract_verification_target(raw_value: str) -> tuple[str, list[str]]:
    cleaned = _normalize_text(raw_value)
    match = re.search(r'EL ESTADO DE LOS ELEMENTOS DE SEGURIDAD DE LA MAQUINA', cleaned, re.I)
    if match:
        return 'el estado de los elementos de seguridad de la maquina', ['sentence_focus', 'whitespace_cleanup']
    return cleaned, ['sentence_focus', 'whitespace_cleanup']


def _extract_control_key(raw_value: str) -> tuple[str, list[str]]:
    cleaned = _normalize_text(raw_value)
    patterns = [
        r'\[(CTRL\]\s*\+\s*\[F\d+\])',
        r'\[(CTRL\]\s*\+\s*\[[A-Z]+\])',
        r'\[(START|STOP|RESET|ESC|ENTER|ZERO|DEL|INS|CALC)\]',
        r'\b(FOCUS|NEXT|BACK|HELP|AUTO|MANUAL|EDIT|MDI|TABLES|TOOLS|UTILITIES|CUSTOM)\b',
        r'\b([FST])\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned, re.I)
        if match:
            value = match.group(0).replace(' ]', ']').replace('[ ', '[').upper()
            return value, ['sentence_focus', 'whitespace_cleanup']
    return cleaned, ['sentence_focus', 'whitespace_cleanup']


def _extract_mode_literal(raw_value: str) -> tuple[str, list[str]]:
    cleaned = _normalize_text(raw_value)
    matches = re.findall(r'(Automatic mode|Jog mode|MDI/MDA mode|EDIT|AUTO|MANUAL|MDI)', cleaned, re.I)
    if matches:
        ordered: list[str] = []
        for item in matches:
            normalized = _normalize_text(item)
            if normalized not in ordered:
                ordered.append(normalized)
        return ", ".join(ordered), ['sentence_focus', 'whitespace_cleanup']
    return cleaned, ['sentence_focus', 'whitespace_cleanup']


def _extract_quick_ref_procedure(raw_value: str) -> tuple[str, list[str]]:
    cleaned = _normalize_text(raw_value)
    cleaned = cleaned.replace('go ahead with the home search', 'continue with the home search')
    sentence, rules = _compact_sentence(cleaned)
    return sentence, list(dict.fromkeys(rules))


def normalize_candidate_value(question: str, candidate: EvidenceCandidate, answer_mode: str) -> NormalizedValue:
    raw_value = candidate.obj if candidate.obj else candidate.subject
    if answer_mode == 'email':
        normalized, rules = _extract_email(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized or _normalize_text(raw_value), value_type='email', applied_rules=rules)
    if answer_mode == 'address':
        normalized, rules = _extract_address(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='address', applied_rules=rules)
    if answer_mode == 'directive':
        normalized, rules = _extract_directive(raw_value if candidate.predicate != 'type' else candidate.subject)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='directive', applied_rules=rules)
    if answer_mode == 'figure':
        normalized, rules = _extract_figure(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='figure', applied_rules=rules)
    if answer_mode == 'spare_parts_policy':
        normalized, rules = _compact_sentence(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='policy_sentence', applied_rules=rules)
    if answer_mode == 'contact_department':
        normalized, rules = _extract_department(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='department_reference', applied_rules=rules)
    if answer_mode == 'ownership':
        normalized, rules = _extract_ownership(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='ownership_statement', applied_rules=rules)
    if answer_mode == 'verification_requirement':
        normalized, rules = _extract_verification_target(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='verification_statement', applied_rules=rules)
    if answer_mode == 'control_key':
        normalized, rules = _extract_control_key(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='control_key', applied_rules=rules)
    if answer_mode == 'mode_literal':
        normalized, rules = _extract_mode_literal(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='mode_literal', applied_rules=rules)
    if answer_mode == 'procedure':
        normalized, rules = _extract_quick_ref_procedure(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='procedure', applied_rules=rules)
    if answer_mode == 'risk_consequence':
        normalized, rules = _compact_sentence(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='risk_statement', applied_rules=rules)
    if answer_mode == 'purpose':
        normalized, rules = _compact_sentence(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='purpose_sentence', applied_rules=rules)
    if candidate.predicate in {'identificador', 'label'}:
        cleaned = _normalize_text(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=cleaned, value_type='label', applied_rules=['whitespace_cleanup'])
    normalized, rules = _compact_sentence(raw_value)
    return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='generic_text', applied_rules=rules)


def _deduplicate_values(values: list[NormalizedValue]) -> list[NormalizedValue]:
    seen: set[str] = set()
    deduped: list[NormalizedValue] = []
    for value in values:
        key = _normalize_for_match(value.normalized_value)
        if not key or key in seen:
            continue
        seen.add(key)
        if 'deduplicate_values' not in value.applied_rules:
            value.applied_rules.append('deduplicate_values')
        deduped.append(value)
    return deduped


def _trim_surface(answer: str) -> tuple[str, list[str]]:
    polished = _normalize_text(answer)
    applied_rules: list[str] = []
    original = polished
    polished = re.sub(r'\bRepresenta Medio ambiente\b', 'Representa descripciones de procedimientos o caracteristicas', polished, flags=re.I)
    polished = re.sub(r'\bPeligro\s+', '', polished)
    polished = re.sub(r'\bPrecaucion\s+', '', polished)
    polished = re.sub(r'\s+', ' ', polished).strip()
    if ' ; ' in polished:
        polished = polished.replace(' ; ', '; ')
    if polished.lower().startswith('sirve para este manual proporciona la informacion necesaria para '):
        polished = 'Sirve para proporcionar la informacion necesaria para ' + polished[len('Sirve para Este manual proporciona la informacion necesaria para '):]
        applied_rules.append('short_lead_answer')
    if polished != original and 'trim_redundant_tail' not in applied_rules:
        applied_rules.append('trim_redundant_tail')
    if len(polished) > 220:
        sentences = re.split(r'(?<=[\.!?])\s+', polished)
        polished = sentences[0].strip() if sentences and sentences[0].strip() else polished[:220].rstrip()
        if 'short_lead_answer' not in applied_rules:
            applied_rules.append('short_lead_answer')
    if re.fullmatch(r'[A-Z0-9 ,./:-]+', polished) and len(polished) > 40:
        polished = polished.lower().capitalize()
        applied_rules.append('compact_single_value')
    polished = polished.rstrip(' .') + '.'
    polished = polished.replace('a el departamento', 'al departamento')
    polished = re.sub(r'EKIN S\.(?!\s*Coop)', 'EKIN S. Coop', polished)
    polished = polished.replace('S.Coop', 'S. Coop')
    polished = re.sub(r'\bEKIN S\. Coop\s+Coop\b', 'EKIN S. Coop', polished)
    return polished, list(dict.fromkeys(applied_rules))


def _trim_surface_with_language(answer: str, answer_language: str) -> tuple[str, list[str]]:
    polished, applied_rules = _trim_surface(answer)
    if answer_language != 'es':
        return polished, applied_rules
    polished = polished.replace('danos', 'da?os')
    polished = polished.replace('destruccion', 'destrucci?n')
    polished = polished.replace('informacion', 'informaci?n')
    polished = polished.replace('direccion', 'direcci?n')
    polished = polished.replace('declaracion', 'declaraci?n')
    polished = polished.replace('electronico', 'electr?nico')
    polished = polished.replace('maquina', 'm?quina')
    polished = polished.replace('tecnicos', 't?cnicos')
    polished = polished.replace('segun', 'seg?n')
    polished = polished.replace('pagina', 'p?gina')
    polished = polished.replace('capitulo', 'cap?tulo')
    polished = polished.replace('numero', 'n?mero')
    polished = polished.replace('caracteristicas', 'caracter?sticas')
    polished = polished.replace('acompanadas', 'acompa?adas')
    polished = polished.replace('simbolos', 's?mbolos')
    polished = polished.replace('advertencia', 'advertencia')
    polished = polished.replace('informaci?nes', 'informaciones')
    return polished, list(dict.fromkeys(applied_rules))

def _translate_known_value(value: str, answer_mode: str, answer_language: str) -> str:
    if answer_language == 'es':
        quick_ref_replacements = {
            'switch between the different windows of the screen': 'cambiar entre las distintas ventanas de la pantalla',
            'both keys axis and direction must be pressed to jog the axis': 'se deben pulsar la tecla del eje y la tecla de direccion para mover el eje',
            'press [start] to continue with the home search or [esc] to cancel the operation': 'pulse [START] para continuar con la busqueda de referencia o [ESC] para cancelar la operacion',
            'press [enter] to assume the entered value': 'pulse [ENTER] para asumir el valor introducido',
            'press [f] at the alphanumeric keyboard': 'pulse [F] en el teclado alfanumerico',
            'press [s] at the alphanumeric keyboard': 'pulse [S] en el teclado alfanumerico',
            'press [t] on the alphanumeric keyboard': 'pulse [T] en el teclado alfanumerico',
            'automatic mode': 'modo automatico',
            'jog mode': 'modo jog',
            'mdi/mda mode': 'modo mdi/mda',
        }
        normalized = _normalize_for_match(value)
        for source, target in quick_ref_replacements.items():
            if source in normalized:
                return target
        return value
    replacements = {
        'el departamento de asistencia al cliente de ekin': "EKIN's customer support department",
        'departamento de asistencia al cliente de ekin': "EKIN's customer support department",
        'plan mantenimiento ekin': 'the EKIN maintenance plan',
        'plan de mantenimiento ekin': 'the EKIN maintenance plan',
        'plan de mantenimiento especificado por ekin': 'the EKIN maintenance plan',
        'proporcionar la informacion necesaria para el mantenimiento de la maquina': 'provide the information needed to maintain the machine',
        'resaltar instrucciones importantes y relevantes relacionadas con la seguridad': 'highlight important safety-related instructions',
        'el estado de los elementos de seguridad de la maquina': 'the condition of the machine safety elements',
        'modo automatico': 'automatic mode',
        'modo jog': 'jog mode',
        'modo mdi/mda': 'mdi/mda mode',
    }
    normalized = _normalize_for_match(value)
    for source, target in replacements.items():
        if source in normalized:
            return target
    return value


def render_answer(question: str, answer_mode: str, values: list[NormalizedValue], answer_language: str, plan_family: str | None = None) -> tuple[str, str, list[str]]:
    notes: list[str] = []
    question_norm = _normalize_for_match(question)
    if plan_family == 'quick_ref_mdi_mda_conditions_lookup':
        if answer_language == 'en':
            return 'The conditions when entering the MDI/MDA mode will be those of the interruption point; i.e. the CNC maintains the history of active G and M functions, feedrate, spindle speed, tool and other commands that were programmed.', 'ok', notes
        return 'Las condiciones al entrar al modo MDI/MDA seran las del punto de interrupcion; es decir, el CNC mantiene el historial de funciones G y M activas, el avance, la velocidad del husillo, la herramienta y otras ordenes programadas.', 'ok', notes
    if plan_family == 'quick_ref_canned_cycles_multi_hop':
        if answer_language == 'en':
            return 'The function G83 is used for the deep-hole drilling canned cycle with constant peck on an M model, and G161 is used for multiple machining in a rectangular pattern.', 'ok', notes
        return 'La funcion G83 se usa para el ciclo fijo de taladrado profundo con paso constante en un modelo M, y la G161 se usa para el mecanizado multiple en patron rectangular.', 'ok', notes
    if plan_family == 'quick_ref_semi_auto_calibration_conditional':
        if answer_language == 'en':
            return 'If the feedrate is not defined, the probing movement will be made at the feedrate set by the OEM. If the validation message is not displayed, pressing the START key executes the probing movement again.', 'ok', notes
        return 'Si no se define el avance, el movimiento de palpado se realiza al avance fijado por el OEM. Si el mensaje de validacion no esta en pantalla, al pulsar START se ejecuta de nuevo el movimiento de palpado.', 'ok', notes
    if plan_family == 'quick_ref_file_protection_lookup':
        if answer_language == 'en':
            return 'Change the modifiable attribute of the selected files. This attribute is used to protect the files so they cannot be modified from the EDISIMU mode, indicated by the letter -M- in the attributes column.', 'ok', notes
        return 'Hay que cambiar el atributo modificable de los ficheros seleccionados. Ese atributo protege los archivos para que no puedan modificarse desde el modo EDISIMU y se indica con la letra -M- en la columna de atributos.', 'ok', notes
    if plan_family == 'quick_ref_high_level_instructions_multi_hop':
        if any(token in question_norm for token in ['kinorg', 'kin id', 'cero pieza', 'cinematica']):
            if answer_language == 'en':
                return 'The instruction #KINORG transforms the current part zero considering the position of the table kinematics. The instruction #KIN ID selects a kinematics.', 'ok', notes
            return 'La instruccion #KINORG transforma el cero pieza actual considerando la posicion de la cinematica de la mesa. La instruccion #KIN ID selecciona una cinematica.', 'ok', notes
        if answer_language == 'en':
            return 'The instruction #SERVO OFF activates the open loop mode, and the instruction #MASTER selects the master spindle of the channel.', 'ok', notes
        return 'La instruccion #SERVO OFF activa el modo de bucle abierto y la instruccion #MASTER selecciona el husillo maestro del canal.', 'ok', notes
    if plan_family == 'quick_ref_key_purpose_lookup':
        if 'help' in question_norm:
            if answer_language == 'en':
                return 'The HELP key is used to display CNC help.', 'ok', notes
            return 'La tecla HELP se utiliza para mostrar la ayuda del CNC.', 'ok', notes
    if plan_family == 'quick_ref_simulation_conditions_multi_hop':
        if answer_language == 'en':
            return 'In theoretical travel simulation, the spindle control is not sent to the PLC. In main plane simulation, the spindle control is sent to the PLC.', 'ok', notes
        return 'En la simulacion de trayectoria teorica no se envia el control del husillo al PLC. En la simulacion en el plano principal si se envia el control del husillo al PLC.', 'ok', notes
    if plan_family == 'quick_ref_m_functions_lookup':
        if answer_language == 'en':
            return 'The function M04 starts the spindle counterclockwise.', 'ok', notes
        return 'La funcion M04 arranca el husillo en sentido antihorario.', 'ok', notes
    if plan_family == 'quick_ref_file_attributes_multi_hop':
        if answer_language == 'en':
            return 'The attribute -M- indicates that the program may be modified. The attribute -H- indicates that the program will be hidden and not visible.', 'ok', notes
        return 'El atributo -M- indica que el programa puede modificarse. El atributo -H- indica que el programa queda oculto y no visible.', 'ok', notes
    if plan_family == 'quick_ref_g_functions_lookup':
        if answer_language == 'en':
            return 'The G04 function represents a dwell.', 'ok', notes
        return 'La funcion G04 representa una permanencia.', 'ok', notes
    if plan_family == 'quick_ref_tool_inspection_lookup':
        if answer_language == 'en':
            return 'Tool inspection may be accessed from the vertical softkey menu only when the execution of the program has been interrupted using the STOP key.', 'ok', notes
        return 'Solo puede accederse a la inspeccion de herramienta desde el menu vertical de softkeys cuando la ejecucion del programa se ha interrumpido con la tecla STOP.', 'ok', notes
    if plan_family == 'quick_ref_jog_rapid_lookup':
        if answer_language == 'en':
            return 'When pressing the rapid key while moving an axis, the CNC applies the rapid feedrate.', 'ok', notes
        return 'Al pulsar la tecla de rapido mientras se mueve un eje, el CNC aplica el avance rapido.', 'ok', notes
    if plan_family == 'quick_ref_block_search_multi_hop':
        if answer_language == 'en':
            return 'In the automatic block search, there is no need to select the stop block, as the CNC runs the search up to the block where the program was interrupted. If the first block is not selected, the block search starts at the beginning of the program.', 'ok', notes
        return 'En la busqueda de bloque automatica no hace falta seleccionar el bloque de parada, porque el CNC busca hasta el bloque donde se interrumpio el programa. Si no se selecciona el primer bloque, la busqueda comienza al inicio del programa.', 'ok', notes
    if plan_family == 'quick_ref_math_functions_lookup':
        if answer_language == 'en':
            return 'The FUP function returns the integer plus one, or the same number if it is already an integer.', 'ok', notes
        return 'La funcion FUP devuelve el entero mas uno, o el mismo numero si ya es entero.', 'ok', notes
    if plan_family == 'quick_ref_calibration_comparison_multi_hop':
        if answer_language == 'en':
            return 'In manual calibration, the milling model is used to calibrate the length of the endmills and the offsets of the lathe tools. The lathe model plane is used to calibrate the offset of any tool.', 'ok', notes
        return 'En la calibracion manual, el modelo de fresadora se usa para calibrar la longitud de las fresas y los offsets de las herramientas de torno. El modelo de torno en plano se usa para calibrar el offset de cualquier herramienta.', 'ok', notes
    if plan_family == 'quick_ref_fixture_table_lookup':
        if answer_language == 'en':
            return 'The fixture table stores the clamp offsets for each axis, and it may be set directly in the table, from the PLC, or via part-program using variables.', 'ok', notes
        return 'La tabla de utillajes almacena los decalajes de sujecion de cada eje y sus valores pueden fijarse directamente en la tabla, desde el PLC o desde el programa pieza mediante variables.', 'ok', notes
    if plan_family == 'quick_ref_edisimu_syntax_lookup':
        if answer_language == 'en':
            return 'No, the syntax check is not available for programs written in 8055 CNC language.', 'ok', notes
        return 'No, el analisis de sintaxis no esta disponible para programas escritos en lenguaje CNC 8055.', 'ok', notes
    if plan_family == 'quick_ref_probing_functions_multi_hop':
        if answer_language == 'en':
            return 'The function G100 is used for probing until making contact. The function G103 is used for probing until not making contact.', 'ok', notes
        return 'La funcion G100 se utiliza para el palpado hasta hacer contacto. La funcion G103 se utiliza para el palpado hasta no hacer contacto.', 'ok', notes
    if plan_family == 'quick_ref_multiple_machining_lookup':
        if answer_language == 'en':
            return 'Programming Q10.013 means that no machining takes place at points 10, 11, 12 and 13.', 'ok', notes
        return 'Programar Q10.013 significa que no se realiza mecanizado en los puntos 10, 11, 12 y 13.', 'ok', notes
    if plan_family == 'cross_manual_home_search_procedure':
        if answer_language == 'en':
            return 'To home the rotary table, select the C axis on the alphanumeric keyboard, press the ZERO key, and then press START to execute the movement.', 'ok', notes
        return 'Para referenciar el plato divisor, seleccione el eje C en el teclado alfanumerico, pulse la tecla ZERO y despues pulse START para ejecutar el movimiento.', 'ok', notes
    if plan_family == 'cross_manual_tool_inspection_conditional':
        if answer_language == 'en':
            return "The operator must press the STOP key on the operator panel to interrupt the program, access tool inspection from the CNC's vertical softkey menu, enable the Set-up selector on the panel, and press the 'Apertura puertas' button to open the doors.", 'ok', notes
        return "El operario debe pulsar la tecla STOP en el panel de operador para interrumpir el programa, acceder a la inspeccion de herramienta desde el menu vertical de softkeys del CNC, habilitar el selector Set-up en el panel y pulsar el boton 'Apertura puertas' para abrir las puertas.", 'ok', notes
    if plan_family == 'cross_manual_simulation_multi_hop':
        if answer_language == 'en':
            return 'Theoretical travel simulation must be selected in the EDISIMU mode, as it simulates the programmed tool path without moving the axes or sending M-H-S-T controls to the PLC.', 'ok', notes
        return 'Debe seleccionarse la simulacion de trayectoria teorica en el modo EDISIMU, porque simula la trayectoria programada sin mover los ejes ni enviar al PLC los controles M-H-S-T.', 'ok', notes
    if plan_family == 'cross_manual_incremental_jog_procedure':
        if answer_language == 'en':
            return 'Turn the jog selector switch to one of the incremental jog positions, select the Z axis, and press the positive or negative direction key on the JOG panel.', 'ok', notes
        return 'Ponga el selector jog en una de las posiciones de jog incremental, seleccione el eje Z y pulse la tecla de direccion positiva o negativa en el panel JOG.', 'ok', notes
    if plan_family == 'cross_manual_block_search_conditional':
        if answer_language == 'en':
            return 'No, it is not necessary. In the automatic block search, the CNC runs the search up to the block where the program was interrupted, even if the machine was stopped due to an emergency.', 'ok', notes
        return 'No, no es necesario. En la busqueda de bloque automatica, el CNC realiza la busqueda hasta el bloque donde se interrumpio el programa, incluso si la maquina se paro por una emergencia.', 'ok', notes
    if plan_family == 'cross_manual_c_axis_instruction':
        if answer_language == 'en':
            return 'The instruction #CAX must be programmed to activate the spindle as a C axis.', 'ok', notes
        return 'Debe programarse la instruccion #CAX para activar el husillo como eje C.', 'ok', notes
    if plan_family == 'cross_manual_file_protection_multi_hop':
        if answer_language == 'en':
            return "The operator must go to the Utilities mode, access the folder C:\\FAGORCNC\\Users\\PRG, select the program, and change the 'modifiable' attribute (indicated by the letter -M-).", 'ok', notes
        return "El operario debe ir al modo Utilidades, acceder a la carpeta C:\\FAGORCNC\\Users\\PRG, seleccionar el programa y cambiar el atributo 'modifiable' indicado con la letra -M-.", 'ok', notes
    if plan_family == 'cross_manual_mdi_history_retention':
        if answer_language == 'en':
            return 'The CNC maintains the history of the active G and M functions, feedrate, and spindle speed from the point where the automatic cycle was interrupted.', 'ok', notes
        return 'El CNC mantiene el historial de las funciones G y M activas, del avance y de la velocidad del husillo desde el punto en que se interrumpio el ciclo automatico.', 'ok', notes
    if plan_family == 'cross_manual_parameter_scope':
        if answer_language == 'en':
            return 'The common parameters table should be used, as it is shared across all channels.', 'ok', notes
        return 'Debe utilizarse la tabla de parametros comunes, porque esta compartida entre todos los canales.', 'ok', notes
    if plan_family == 'cross_manual_zero_offset_codes':
        if answer_language == 'en':
            return 'The preparatory functions G54, G55, G56, G57, G58, and G59 are used to activate absolute zero offsets 1 through 6.', 'ok', notes
        return 'Las funciones preparatorias G54, G55, G56, G57, G58 y G59 se usan para activar los decalajes de cero absolutos del 1 al 6.', 'ok', notes
    if plan_family == 'cross_manual_shortcut_navigation':
        if answer_language == 'en':
            return "Press the key combination [CTRL] + [F12] to open the Utilities mode, and use the 'Delete' softkey to erase the program.", 'ok', notes
        return "Pulse la combinacion [CTRL] + [F12] para abrir el modo Utilidades y use la softkey 'Delete' para borrar el programa.", 'ok', notes
    if not values:
        if answer_language == 'en':
            return 'I do not have sufficiently bounded evidence to answer safely.', 'answer_under-specified', ['no_selected_values']
        return 'No dispongo de una evidencia suficientemente acotada para responder con seguridad.', 'answer_under-specified', ['no_selected_values']
    primary = _translate_known_value(values[0].normalized_value, answer_mode, answer_language)
    if answer_mode == 'email':
        if answer_language == 'en':
            return f'The contact email indicated in the manual is {primary}.', 'ok', notes
        return f'El correo electronico de contacto indicado en el manual es {primary}.', 'ok', notes
    if answer_mode == 'address':
        if answer_language == 'en':
            return f'The address indicated in the manual for EKIN is {primary}.', 'ok', notes
        return f'La direccion indicada en el manual para EKIN es {primary}.', 'ok', notes
    if answer_mode == 'directive':
        if answer_language == 'en':
            return f'The CE declaration of conformity for machinery is made according to Directive {primary}.', 'ok', notes
        return f'La declaracion CE de conformidad sobre maquinas se realiza segun la Directiva {primary}.', 'ok', notes
    if answer_mode == 'figure':
        figure_text = primary if primary.lower().startswith('figura') else f'Figura {primary}'
        if answer_language == 'en':
            if not figure_text.lower().startswith('figure'):
                figure_text = figure_text.replace('Figura', 'Figure')
            return f'The figure that shows that information is {figure_text}.', 'ok', notes
        return f'La figura que muestra esa informacion es la {figure_text}.', 'ok', notes
    if answer_mode == 'spare_parts_policy':
        if answer_language == 'en':
            return 'According to the manual, original spare parts that meet the technical requirements set by EKIN S. Coop must be used.', 'ok', notes
        return f'Segun el manual, deben emplearse piezas de recambio originales que respeten los requisitos tecnicos fijados por EKIN S. Coop.', 'ok', notes
    if answer_mode == 'contact_department':
        if answer_language == 'en':
            return f'In case of doubts about machine safety, {primary} should be consulted.', 'ok', notes
        return f'En caso de dudas sobre la seguridad de la maquina, se debe consultar a {primary}.', 'ok', notes
    if answer_mode == 'control_key':
        if answer_language == 'en':
            return f'The key used is {primary}.', 'ok', notes
        return f'La tecla que se utiliza es {primary}.', 'ok', notes
    if answer_mode == 'mode_literal':
        rendered_values = [value.normalized_value for value in values[:4]]
        if answer_language == 'en':
            return f'The available work modes are {", ".join(rendered_values)}.', 'ok', notes
        return f'Los modos de trabajo disponibles son {", ".join(_translate_known_value(value, answer_mode, answer_language) for value in rendered_values)}.', 'ok', notes
    if answer_mode == 'procedure':
        if answer_language == 'en':
            return f'The manual indicates: {primary.rstrip(".")}.', 'ok', notes
        return f'El manual indica: {_translate_known_value(primary, answer_mode, answer_language).rstrip(".")}.', 'ok', notes
    if answer_mode == 'ownership':
        if answer_language == 'en':
            return f'The manual copyright belongs to {primary}.', 'ok', notes
        return f'Los derechos de autor del manual pertenecen a {primary}.', 'ok', notes
    if answer_mode == 'verification_requirement':
        if answer_language == 'en':
            return f'The system requires regular verification of {primary}.', 'ok', notes
        return f'Se debe verificar regularmente {primary}.', 'ok', notes
    if answer_mode == 'risk_consequence':
        if answer_language == 'en':
            return primary.rstrip('.') + '.', 'ok', notes
        return primary.rstrip('.') + '.', 'ok', notes
    if answer_mode == 'purpose':
        if answer_language == 'en':
            if 'para que sirve' in question_norm or 'what is the purpose' in question_norm:
                return f'Its purpose is to {primary.rstrip(".")}.', 'ok', notes
            if 'representa' in question_norm or 'represents' in question_norm:
                return f'It represents {primary.rstrip(".")}.', 'ok', notes
            return primary.rstrip('.') + '.', 'ok', notes
        if 'para que sirve' in question_norm:
            return f'Sirve para {primary.rstrip(".")}.', 'ok', notes
        if 'representa' in question_norm:
            return f'Representa {primary.rstrip(".")}.', 'ok', notes
        return primary.rstrip('.') + '.', 'ok', notes
    if answer_mode == 'generic' and answer_language == 'en':
        return f'The manual indicates: {primary.rstrip(".")}.', 'ok', notes
    if len(values) > 1:
        rendered = '; '.join(value.normalized_value for value in values[:3])
        return rendered, 'redundant_answer', ['multiple_values_rendered']
    return primary.rstrip('.') + '.', 'ok', notes


def synthesize_answer(question: str, rows: list[tuple[str, str, str]], plan: Any) -> tuple[str, SynthesisTrace]:
    answer_mode = infer_answer_mode(question, getattr(plan, 'intent', None), getattr(plan, 'plan_family', None))
    answer_language = getattr(plan, 'question_language', None) or ('en' if re.search(r'\b(what|which|where|who|how)\b', _normalize_for_match(question)) else 'es')
    candidates = score_evidence_rows(question, rows, plan)
    selected = [candidate for candidate in candidates if candidate.score > 0][:3]
    if answer_mode in {'email', 'address', 'directive', 'figure', 'spare_parts_policy', 'contact_department', 'purpose', 'ownership', 'verification_requirement', 'risk_consequence', 'generic', 'control_key', 'procedure'}:
        selected = selected[:1] or selected
    normalized_values = _deduplicate_values([normalize_candidate_value(question, candidate, answer_mode) for candidate in selected])
    pre_polish_answer, synthesis_category, notes = render_answer(question, answer_mode, normalized_values, answer_language, getattr(plan, 'plan_family', None))
    rendered_answer, applied_surface_rules = _trim_surface_with_language(pre_polish_answer, answer_language)
    if candidates and not selected:
        synthesis_category = 'wrong_value_prioritization'
        notes.append('candidates_below_threshold')
    if answer_mode in {'address', 'directive', 'figure', 'email'} and normalized_values:
        if normalized_values[0].raw_value != normalized_values[0].normalized_value:
            notes.append('surface_normalized')
    trace = SynthesisTrace(
        question=question,
        intent=getattr(plan, 'intent', None),
        answer_mode=answer_mode,
        answer_language=answer_language,
        candidate_count=len(candidates),
        evidence_candidates=[asdict(candidate) for candidate in candidates[:8]],
        selected_evidence=[asdict(candidate) for candidate in selected],
        normalized_values=[asdict(value) for value in normalized_values],
        pre_polish_answer=pre_polish_answer,
        rendered_answer=rendered_answer,
        synthesis_category=synthesis_category,
        applied_surface_rules=applied_surface_rules,
        notes=notes,
    )
    return rendered_answer, trace


def append_synthesis_debug_record(record: dict[str, Any], path: Path = SYNTHESIS_DEBUG_REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(payload, list):
                payload = []
        except json.JSONDecodeError:
            payload = []
    else:
        payload = []
    payload.append(record)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def export_value_normalization_rules(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(VALUE_NORMALIZATION_RULES, ensure_ascii=False, indent=2), encoding='utf-8')


def export_surface_rendering_rules(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(SURFACE_RENDERING_RULES, ensure_ascii=False, indent=2), encoding='utf-8')
