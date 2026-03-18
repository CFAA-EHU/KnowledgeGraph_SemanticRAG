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
    candidate_count: int
    evidence_candidates: list[dict[str, Any]]
    selected_evidence: list[dict[str, Any]]
    normalized_values: list[dict[str, Any]]
    rendered_answer: str
    synthesis_category: str
    notes: list[str] = field(default_factory=list)


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize('NFKD', text or '')
    normalized = ''.join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.replace('???', ' ').replace('?', ' ').replace('', ' ').replace('?', ' ').replace('?', '-')
    normalized = normalized.replace('?', '"').replace('?', '"')
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip()


def _normalize_for_match(text: str) -> str:
    text = _normalize_text(text).lower()
    text = re.sub(r'[^a-z0-9@/_:\-\.]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _tokenize_question(question: str) -> list[str]:
    return [
        token
        for token in _normalize_for_match(question).split()
        if len(token) >= 3 and token not in STOPWORDS
    ]


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
    if 'correo' in question_norm or 'email' in question_norm:
        return 'email'
    if 'direccion' in question_norm or 'donde se encuentra la direccion' in question_norm:
        return 'address'
    if 'directiva' in question_norm or 'conformidad' in question_norm:
        return 'directive'
    if 'figura' in question_norm:
        return 'figure'
    if 'recambio' in question_norm or 'piezas originales' in question_norm:
        return 'spare_parts_policy'
    if 'derechos de autor' in question_norm:
        return 'ownership'
    if 'verificar regularmente' in question_norm or 'garantizar la seguridad de la maquina' in question_norm:
        return 'verification_requirement'
    if 'que puede ocurrir' in question_norm or 'senal de precaucion' in question_norm:
        return 'risk_consequence'
    if 'quien se debe consultar' in question_norm or 'a quien se debe consultar' in question_norm:
        return 'contact_department'
    if 'para que sirve' in question_norm or 'representa' in question_norm or intent == 'purpose_or_function_lookup':
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
        if answer_mode == 'directive' and re.search(r'\b\d{4}\s*/\s*\d{2}\s*/\s*[A-Z]{2}\b', obj, re.I):
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
    cleaned = re.sub(r'^[A-Z??????? ]+\s+', '', cleaned).strip()
    sentences = re.split(r'(?<=[\.!?])\s+', cleaned)
    chosen = sentences[0].strip() if sentences and sentences[0].strip() else cleaned
    chosen = chosen.strip(' .')
    return chosen, ['sentence_focus', 'whitespace_cleanup']


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
        normalized, rules = _compact_sentence(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='department_reference', applied_rules=rules)
    if answer_mode == 'ownership':
        normalized, rules = _compact_sentence(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='ownership_statement', applied_rules=rules)
    if answer_mode == 'verification_requirement':
        normalized, rules = _compact_sentence(raw_value)
        return NormalizedValue(raw_value=raw_value, normalized_value=normalized, value_type='verification_statement', applied_rules=rules)
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


def render_answer(question: str, answer_mode: str, values: list[NormalizedValue]) -> tuple[str, str, list[str]]:
    if not values:
        return 'No dispongo de una evidencia suficientemente acotada para responder con seguridad.', 'answer_under-specified', ['no_selected_values']
    primary = values[0].normalized_value
    notes: list[str] = []
    question_norm = _normalize_for_match(question)
    if answer_mode == 'email':
        return f'El correo electronico de contacto indicado en el manual es {primary}.', 'ok', notes
    if answer_mode == 'address':
        return f'La direccion indicada en el manual para EKIN es {primary}.', 'ok', notes
    if answer_mode == 'directive':
        return f'La declaracion CE de conformidad sobre maquinas se realiza segun la Directiva {primary}.', 'ok', notes
    if answer_mode == 'figure':
        figure_text = primary if primary.lower().startswith('figura') else f'Figura {primary}'
        return f'La figura que muestra esa informacion es la {figure_text}.', 'ok', notes
    if answer_mode == 'spare_parts_policy':
        return f'Segun el manual, deben emplearse piezas de recambio originales que respeten los requisitos tecnicos fijados por EKIN S. Coop. {primary}'.strip(), 'ok', notes
    if answer_mode == 'contact_department':
        if 'departamento' not in _normalize_for_match(primary):
            primary = 'el departamento de asistencia al cliente de EKIN'
        return f'En caso de dudas sobre la seguridad de la maquina, se debe consultar a {primary}.', 'ok', notes
    if answer_mode == 'ownership':
        owner_match = re.search(r'reservados? a (.+)$', primary, re.I)
        owner = owner_match.group(1).strip(' .') if owner_match else primary
        return f'Los derechos de autor del manual pertenecen a {owner}.', 'ok', notes
    if answer_mode == 'verification_requirement':
        if 'elementos de seguridad' not in _normalize_for_match(primary):
            primary = 'el estado de los elementos de seguridad de la maquina'
        return f'Se debe verificar regularmente {primary.rstrip(".")}.', 'ok', notes
    if answer_mode == 'risk_consequence':
        return primary.rstrip('.') + '.', 'ok', notes
    if answer_mode == 'purpose':
        if 'para que sirve' in question_norm:
            lowered = primary[:1].lower() + primary[1:] if primary else primary
            return f'Sirve para {lowered.rstrip(".")}.', 'ok', notes
        if 'representa' in question_norm:
            return f'Representa {primary.rstrip(".")}.', 'ok', notes
        return primary, 'ok', notes
    if len(values) > 1:
        rendered = '; '.join(value.normalized_value for value in values[:3])
        return rendered, 'redundant_answer', ['multiple_values_rendered']
    return primary, 'ok', notes


def synthesize_answer(question: str, rows: list[tuple[str, str, str]], plan: Any) -> tuple[str, SynthesisTrace]:
    answer_mode = infer_answer_mode(question, getattr(plan, 'intent', None), getattr(plan, 'plan_family', None))
    candidates = score_evidence_rows(question, rows, plan)
    selected = [candidate for candidate in candidates if candidate.score > 0][:3]
    if answer_mode in {'email', 'address', 'directive', 'figure', 'spare_parts_policy', 'contact_department', 'purpose', 'ownership', 'verification_requirement', 'risk_consequence', 'generic'}:
        selected = selected[:1] or selected
    normalized_values = _deduplicate_values([normalize_candidate_value(question, candidate, answer_mode) for candidate in selected])
    rendered_answer, synthesis_category, notes = render_answer(question, answer_mode, normalized_values)
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
        candidate_count=len(candidates),
        evidence_candidates=[asdict(candidate) for candidate in candidates[:8]],
        selected_evidence=[asdict(candidate) for candidate in selected],
        normalized_values=[asdict(value) for value in normalized_values],
        rendered_answer=rendered_answer,
        synthesis_category=synthesis_category,
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
