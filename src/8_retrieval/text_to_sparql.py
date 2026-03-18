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
from typing import Any

from rdflib import Graph, URIRef

from artifact_contracts import (
    MULTIHOP_PLAN_CATALOG_PATH,
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
    QA_MULTIHOP_PATH,
    QUERY_DEBUG_REPORT_PATH,
    QUERY_INTENT_CATALOG_PATH,
)

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
}

INTENT_TRIGGER_RULES = [
    ("figure_or_reference_lookup", ["figura", "seccion", "capitulo", "referencia"]),
    ("regulatory_lookup", ["directiva", "conformidad", "precaucion", "peligro", "medio ambiente", "seguridad", "mantenimiento"]),
    ("literal_lookup", ["correo", "email", "direccion", "telefono", "codigo", "quien"]),
    ("component_attribute_lookup", ["verificar", "estado", "elementos", "componente"]),
    ("component_relation_lookup", ["regla lineal", "controla", "asociado", "relaciona", "subcomponente"]),
    ("purpose_or_function_lookup", ["para que sirve", "objetivo", "indica", "representa", "funcion"]),
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


@dataclass
class QuestionParse:
    intent: str
    anchor_text: str | None
    anchor_candidates: list[str]
    qualifiers: list[str]


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
    error: str | None = None


@dataclass
class QueryExecutionTrace:
    steps: list[QueryStepTrace] = field(default_factory=list)


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
    return parser.parse_args()


MULTIHOP_PLAN_FAMILIES = [
    {
        "family_id": "machine_directive_compliance",
        "template_id": "MH_T1_machine_directive",
        "intent": "regulatory_lookup",
        "hop_depth": 2,
        "keywords_any": [["directiva"], ["conformidad", "cumple"]],
        "seed_uris": [f"{BASE_URI}MaquinaBrochadoExterior_18"],
        "steps": [
            {"step_id": "seed", "purpose": "seed_machine", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}MaquinaBrochadoExterior_18"], "max_candidates": 1, "max_results": 1},
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
        "hop_depth": 2,
        "keywords_any": [["figura"], ["manual", "a218"]],
        "seed_uris": [f"{BASE_URI}ManualBrochadoraA218"],
        "steps": [
            {"step_id": "seed", "purpose": "seed_manual", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}ManualBrochadoraA218"], "max_candidates": 1, "max_results": 1},
            {"step_id": "rel_1", "purpose": "manual_to_figure", "mode": "relation_traverse", "relation": "ilustradoEn", "incoming": True, "target_filters": ["figura0-1-1", "figura"], "max_candidates": 4, "max_results": 10},
            {"step_id": "detail", "purpose": "figure_details", "mode": "describe_entities", "preferred_predicates": ["label", "textoExtracto", "ilustradoEn", "type"], "max_candidates": 4, "max_results": 12},
        ],
    },
    {
        "family_id": "column_component_control_chain",
        "template_id": "MH_T5_parent_component_control",
        "intent": "component_relation_lookup",
        "hop_depth": 3,
        "keywords_any": [["regla", "lineal"], ["columna_46", "columna 46", "componente"]],
        "seed_uris": [f"{BASE_URI}Columna_46"],
        "steps": [
            {"step_id": "seed", "purpose": "seed_parent_component", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}Columna_46"], "max_candidates": 1, "max_results": 1},
            {"step_id": "rel_1", "purpose": "parent_to_child_component", "mode": "relation_traverse", "relation": "tieneComponente", "target_filters": ["carroportapiezas_46", "carroportapiezas"], "max_candidates": 4, "max_results": 10},
            {"step_id": "rel_2", "purpose": "child_component_to_rule", "mode": "relation_traverse", "relation": "controla", "max_candidates": 4, "max_results": 8},
            {"step_id": "detail", "purpose": "rule_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "type"], "max_candidates": 4, "max_results": 12},
        ],
    },
    {
        "family_id": "component_control_chain",
        "template_id": "MH_T4_component_control",
        "intent": "component_relation_lookup",
        "hop_depth": 2,
        "keywords_any": [["regla", "lineal"], ["carro", "porta", "piezas", "46"]],
        "seed_uris": [f"{BASE_URI}CarroPortaPiezas_46"],
        "steps": [
            {"step_id": "seed", "purpose": "seed_component", "mode": "fixed_seed", "fixed_uris": [f"{BASE_URI}CarroPortaPiezas_46"], "max_candidates": 1, "max_results": 1},
            {"step_id": "rel_1", "purpose": "component_to_rule", "mode": "relation_traverse", "relation": "controla", "max_candidates": 4, "max_results": 8},
            {"step_id": "detail", "purpose": "rule_details", "mode": "describe_entities", "preferred_predicates": ["textoExtracto", "label", "identificador", "type"], "max_candidates": 4, "max_results": 12},
        ],
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



def tokenize_question(question: str) -> list[str]:
    tokens = []
    for token in normalize_text(question).split():
        if len(token) < 3 or token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens



def extract_reference_tokens(question: str) -> list[str]:
    normalized = normalize_text(question)
    refs = re.findall(r"\b\d+(?:[-.]\d+)+\b", normalized)
    alphanum = re.findall(r"\b[a-z]*\d+[a-z0-9/_-]*\b", normalized)
    emails = re.findall(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", normalized)
    seen: list[str] = []
    for token in refs + alphanum + emails:
        if token not in seen:
            seen.append(token)
    return seen



def detect_intent(question: str) -> str:
    normalized = normalize_text(question)
    for intent, triggers in INTENT_TRIGGER_RULES:
        if any(trigger in normalized for trigger in triggers):
            return intent
    return "literal_lookup"



def extract_anchor_text(question: str) -> str | None:
    refs = extract_reference_tokens(question)
    if refs:
        return refs[0]
    normalized = normalize_text(question)
    for anchor in ["ekin", "a218", "precaucion", "peligro", "medio ambiente", "seguridad", "columna_46", "46"]:
        if anchor in normalized:
            return anchor
    return None



def build_question_parse(question: str) -> QuestionParse:
    intent = detect_intent(question)
    anchor_text = extract_anchor_text(question)
    tokens = tokenize_question(question)
    candidates: list[str] = []
    if anchor_text:
        candidates.append(anchor_text)
    for token in extract_reference_tokens(question) + tokens:
        if token not in candidates:
            candidates.append(token)
    qualifiers = [token for token in tokens if token not in candidates][:6]
    return QuestionParse(intent=intent, anchor_text=anchor_text, anchor_candidates=candidates[:8], qualifiers=qualifiers)



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



def select_multihop_family(parse: QuestionParse, question: str) -> dict[str, Any] | None:
    normalized = normalize_text(question)
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
    candidate_uris = _rank_generic_candidates(graph, parse, tokens, limit=8)
    fallback_used = not bool(candidate_uris)
    steps: list[QueryStep] = []
    if candidate_uris:
        steps.append(QueryStep(step_id="seed", purpose="seed_from_candidates", mode="fixed_seed", fixed_uris=candidate_uris, max_candidates=8, max_results=8))
        steps.append(QueryStep(step_id="detail", purpose="describe_candidates", mode="describe_entities", preferred_predicates=PREFERRED_LITERAL_PREDICATES, max_candidates=8, max_results=25 if parse.intent == "literal_lookup" else 35))
        sparql = build_describe_query(candidate_uris, PREFERRED_LITERAL_PREDICATES, max_results=25 if parse.intent == "literal_lookup" else 35)
    else:
        pattern = build_regex_pattern(tokens + parse.qualifiers)
        sparql = (
            f"PREFIX ex: <{BASE_URI}>\n"
            "SELECT DISTINCT ?s ?p ?o WHERE {\n"
            "  ?s ?p ?o .\n"
            f"  FILTER(REGEX(STR(?s), \"{pattern}\", \"i\") || REGEX(STR(?o), \"{pattern}\", \"i\"))\n"
            f"}} LIMIT {25 if parse.intent == 'literal_lookup' else 35}"
        )
        steps.append(QueryStep(step_id="fallback", purpose="generic_fallback", mode="fallback_query", max_candidates=25, max_results=25 if parse.intent == "literal_lookup" else 35))
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
        debug={"qualifiers": parse.qualifiers, "seed_candidates": candidate_uris},
    )



def build_query_plan(question: str, schema_text: str, graph: Graph | None = None) -> QueryPlan:
    parse = build_question_parse(question)
    family = select_multihop_family(parse, question)
    if family is not None:
        steps = [QueryStep(**step) for step in family["steps"]]
        plan = QueryPlan(
            intent=family["intent"],
            anchor_text=parse.anchor_text,
            anchor_candidates=parse.anchor_candidates,
            template_id=family["template_id"],
            plan_family=family["family_id"],
            predicted_hop_depth=family["hop_depth"],
            fallback_used=False,
            sparql="",
            steps=steps,
            debug={"qualifiers": parse.qualifiers, "question_parse": asdict(parse), "schema_excerpt_used": bool(schema_text)},
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
    plan.debug.update({"question_parse": asdict(parse), "schema_excerpt_used": bool(schema_text)})
    return plan



def _boundedness_status(raw_result_count: int, output_count: int, pruned_count: int, step: QueryStep) -> str:
    if raw_result_count == 0 or output_count == 0:
        return "too_narrow"
    if pruned_count > 0 or raw_result_count > step.max_results or output_count > step.max_candidates:
        return "too_broad"
    return "bounded"



def _filter_uris(uris: list[str], filters: list[str]) -> list[str]:
    if not filters:
        return uris
    lowered_filters = [token.lower() for token in filters]
    filtered = []
    for uri in uris:
        local = normalize_uri(uri).lower()
        if any(token in local for token in lowered_filters):
            filtered.append(uri)
    return filtered or uris



def execute_query_plan(plan: QueryPlan, graph: Graph) -> QueryExecutionResult:
    aggregated_rows: list[tuple[str, str, str]] = []
    raw_bindings: list[tuple[str, ...]] = []
    seen_rows: set[tuple[str, str, str]] = set()
    seed_uris: list[str] = []
    trace_steps: list[QueryStepTrace] = []

    for step in plan.steps:
        query_text = ""
        raw_rows: list[tuple[str, ...]] = []
        output_uris: list[str] = []
        pruned_count = 0
        error = None
        try:
            if step.mode == "fixed_seed":
                output_uris = step.fixed_uris[: step.max_candidates]
                query_text = build_seed_query(step.fixed_uris)
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
                candidate_uris = _filter_uris(candidate_uris, step.target_filters)
                output_uris = candidate_uris[: step.max_candidates]
                pruned_count = max(0, len(candidate_uris) - len(output_uris))
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
                    if row[2].startswith("http") and row[2] not in described_uris:
                        described_uris.append(row[2])
                output_uris = described_uris[: step.max_candidates]
                pruned_count = max(0, len(described_uris) - len(output_uris))
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
                output_uris = []
            else:
                error = f"unsupported_mode:{step.mode}"
        except Exception as exc:
            error = str(exc)
        if output_uris:
            seed_uris = output_uris
        status = _boundedness_status(len(raw_rows), len(output_uris) if step.mode != "describe_entities" else len(seed_uris), pruned_count, step) if error is None else "error"
        trace_steps.append(
            QueryStepTrace(
                step_id=step.step_id,
                purpose=step.purpose,
                mode=step.mode,
                query_text=query_text,
                input_candidate_count=len(seed_uris) if step.step_id != "seed" else len(step.fixed_uris),
                raw_result_count=len(raw_rows),
                output_candidate_count=len(output_uris),
                pruned_count=pruned_count,
                boundedness_status=status,
                output_uris=output_uris,
                sample_rows=[[normalize_uri(value) if value.startswith("http") else value for value in row] for row in raw_rows[:6]],
                error=error,
            )
        )
        if error is not None:
            break

    plan.debug["step_count"] = len(plan.steps)
    plan.debug["result_count"] = len(aggregated_rows)
    plan.debug["final_candidate_count"] = len(seed_uris)
    plan.debug["trace_summary"] = [asdict(item) for item in trace_steps]
    if trace_steps:
        plan.sparql = trace_steps[-1].query_text
    return QueryExecutionResult(plan=plan, rows=aggregated_rows, raw_bindings=raw_bindings, trace=QueryExecutionTrace(steps=trace_steps))



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
    benchmark_map = {item["canonical_sparql_id"]: item for item in benchmark.get("questions", [])}
    families = []
    mapping = {
        "machine_directive_compliance": "mh_005",
        "system_maintenance_plan": "mh_001",
        "manual_figure_reference": "mh_003",
        "component_control_chain": "mh_006",
        "column_component_control_chain": "mh_007",
    }
    by_question_id = {item["question_id"]: item for item in benchmark.get("questions", [])}
    seen_family_ids: set[str] = set()
    for family in MULTIHOP_PLAN_FAMILIES:
        if family["family_id"] in seen_family_ids:
            continue
        seen_family_ids.add(family["family_id"])
        benchmark_example = by_question_id.get(mapping.get(family["family_id"], ""), {})
        families.append({
            "family_id": family["family_id"],
            "template_id": family["template_id"],
            "intent": family["intent"],
            "hop_depth": family["hop_depth"],
            "example_question": benchmark_example.get("question"),
            "expected_path": benchmark_example.get("expected_path"),
            "seed_uris": family["seed_uris"],
            "step_modes": [step["mode"] for step in family["steps"]],
            "relations": [step.get("relation") for step in family["steps"] if step.get("relation")],
        })
    payload = {"catalog_version": "t12_v1", "families": families}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload



def main() -> None:
    args = parse_args()
    if args.export_plan_catalog:
        payload = export_multihop_plan_catalog()
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
