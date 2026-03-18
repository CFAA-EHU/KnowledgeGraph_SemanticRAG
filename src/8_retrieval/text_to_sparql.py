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
from typing import Callable

from rdflib import Graph, URIRef

from artifact_contracts import (
    OPERATIONAL_ABOX_PATH,
    OPERATIONAL_TBOX_PATH,
    QUERY_DEBUG_REPORT_PATH,
    QUERY_INTENT_CATALOG_PATH,
)

TBOX_PATH = OPERATIONAL_TBOX_PATH
ABOX_PATH = OPERATIONAL_ABOX_PATH
BASE_URI = "https://vocab.cfaa.eus/broaching/"
MAX_CANDIDATES = 16

STOPWORDS = {
    "de", "la", "el", "los", "las", "del", "para", "por", "que", "una", "uno", "segun", "sobre",
    "esta", "este", "estos", "estas", "cual", "donde", "quien", "como", "manual", "maquina",
    "indicado", "indicada", "mencionada", "respecto", "debe", "deben", "tipo", "informacion", "aparece",
    "sirve", "hace", "muestra", "realiza", "utilizados", "pregunta",
}

INTENT_TRIGGER_RULES = [
    ("figure_or_reference_lookup", ["figura", "seccion", "capitulo", "referencia"]),
    ("regulatory_lookup", ["directiva", "conformidad", "precaucion", "peligro", "medio ambiente", "seguridad"]),
    ("literal_lookup", ["correo", "email", "direccion", "telefono", "codigo", "quien"]),
    ("component_attribute_lookup", ["verificar", "estado", "elementos", "componente"]),
    ("component_relation_lookup", ["relacion", "conecta", "asociado", "relaciona"]),
    ("purpose_or_function_lookup", ["para que sirve", "objetivo", "indica", "representa", "funcion"]),
]


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
    sparql: str


@dataclass
class QueryPlan:
    intent: str
    anchor_text: str | None
    anchor_candidates: list[str]
    template_id: str
    sparql: str
    fallback_used: bool
    debug: dict[str, object] = field(default_factory=dict)
    queries: list[QueryStep] = field(default_factory=list)
    candidate_query: str | None = None
    expansion_query: str | None = None


@dataclass
class QueryExecutionResult:
    plan: QueryPlan
    rows: list[tuple[str, str, str]]
    raw_bindings: list[tuple[str, str, str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Planner compartido de consultas SPARQL por intencion.")
    parser.add_argument("question", nargs="?", default="?Segun que directiva se realiza la declaracion CE de conformidad sobre maquinas?")
    return parser.parse_args()


def cargar_grafo_memoria() -> Graph:
    if not TBOX_PATH.exists() or not ABOX_PATH.exists():
        raise SystemExit("Error: Faltan archivos T-Box o A-Box.")
    graph = Graph()
    graph.parse(TBOX_PATH, format="turtle")
    graph.parse(ABOX_PATH, format="turtle")
    return graph


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = text.replace("?", " ").replace("?", " ")
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
    seen = []
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
    if "ekin" in normalized:
        return "ekin"
    if "manual" in normalized and "a218" in normalized:
        return "a218"
    if "precaucion" in normalized:
        return "precaucion"
    if "peligro" in normalized:
        return "peligro"
    if "medio ambiente" in normalized:
        return "medio ambiente"
    if "seguridad" in normalized:
        return "seguridad"
    return None


def build_question_parse(question: str) -> QuestionParse:
    intent = detect_intent(question)
    anchor_text = extract_anchor_text(question)
    tokens = tokenize_question(question)
    candidates = []
    if anchor_text:
        candidates.append(anchor_text)
    for token in extract_reference_tokens(question) + tokens:
        if token not in candidates:
            candidates.append(token)
    qualifiers = [token for token in tokens if token not in candidates][:5]
    return QuestionParse(
        intent=intent,
        anchor_text=anchor_text,
        anchor_candidates=candidates[:6],
        qualifiers=qualifiers,
    )


def build_regex_pattern(tokens: list[str]) -> str:
    usable = [token for token in tokens if token]
    if not usable:
        usable = ["manual"]
    escaped = [re.escape(token) for token in usable[:6]]
    return "|".join(escaped)


def build_contains_clauses(var_s: str, var_o: str, tokens: list[str]) -> str:
    clauses = []
    for token in tokens[:4]:
        token_lower = token.lower()
        clauses.append(f'CONTAINS(LCASE(STR({var_s})), "{token_lower}")')
        clauses.append(f'CONTAINS(LCASE(STR({var_o})), "{token_lower}")')
    return " || ".join(clauses) if clauses else 'CONTAINS(LCASE(STR(?o)), "manual")'


def select_candidate_uris(graph: Graph | None, anchor_candidates: list[str]) -> list[str]:
    if graph is None:
        return []

    ranked: dict[str, int] = {}
    for candidate in anchor_candidates:
        candidate_lower = candidate.lower()
        query = (
            "SELECT DISTINCT ?s ?o WHERE {\n"
            "  ?s ?p ?o .\n"
            f"  FILTER(CONTAINS(LCASE(STR(?s)), \"{candidate_lower}\") || CONTAINS(LCASE(STR(?o)), \"{candidate_lower}\"))\n"
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
    ordered = sorted(ranked.items(), key=lambda item: (-item[1], item[0]))
    return [uri for uri, _ in ordered[:MAX_CANDIDATES]]


def rerank_candidate_uris(candidate_uris: list[str], parse: QuestionParse, *, limit: int = 8) -> list[str]:
    qualifiers = {token.lower() for token in parse.qualifiers}
    preferred_fragments: list[str] = []
    if parse.intent == "literal_lookup":
        if parse.anchor_text and parse.anchor_text.lower() == "ekin":
            preferred_fragments.extend(["empresa", "departamento", "ekin", "manual"])
        if {"correo", "email", "direccion", "telefono"}.intersection(qualifiers):
            preferred_fragments.extend(["empresa", "departamento", "contacto", "manual"])
        if {"recambio", "piezas", "pieza"}.intersection(qualifiers):
            preferred_fragments.extend(["piezarecambio", "empresa"])
    if parse.intent == "regulatory_lookup":
        if parse.anchor_text and parse.anchor_text.lower() == "ekin":
            preferred_fragments.extend(["departamento", "empresa", "ekin"])
        preferred_fragments.extend(["directiva", "indicacion", "instruccion", "aviso"])
    if parse.intent == "figure_or_reference_lookup":
        preferred_fragments.extend(["figura"])

    def score(uri: str) -> tuple[int, int, str]:
        local = normalize_uri(uri).lower()
        fragment_hits = sum(1 for fragment in preferred_fragments if fragment in local)
        anchor_hit = 1 if parse.anchor_text and parse.anchor_text.lower() in local else 0
        return (-fragment_hits, -anchor_hit, local)

    ordered = sorted(candidate_uris, key=score)
    seen: list[str] = []
    for uri in ordered:
        if uri not in seen:
            seen.append(uri)
    return seen[:limit]


def build_candidate_query(tokens: list[str], *, limit: int = 10) -> str:
    clauses = build_contains_clauses("?s", "?o", tokens)
    return (
        "SELECT DISTINCT ?s WHERE {\n"
        "  ?s ?p ?o .\n"
        f"  FILTER({clauses})\n"
        "} LIMIT " + str(limit)
    )


def build_expansion_query(candidate_uris: list[str], *, incoming: bool = False, limit: int = 40) -> str:
    values = " ".join(f"<{uri}>" for uri in candidate_uris)
    if incoming:
        return (
            "SELECT DISTINCT ?x ?p ?s WHERE {\n"
            f"  VALUES ?s {{ {values} }}\n"
            "  ?x ?p ?s .\n"
            "} LIMIT " + str(limit)
        )
    return (
        "SELECT DISTINCT ?s ?p ?o WHERE {\n"
        f"  VALUES ?s {{ {values} }}\n"
        "  ?s ?p ?o .\n"
        "} LIMIT " + str(limit)
    )


def _build_fallback_query(tokens: list[str], *, limit: int = 20) -> str:
    pattern = build_regex_pattern(tokens)
    return (
        f"PREFIX ex: <{BASE_URI}>\n"
        "SELECT DISTINCT ?s ?p ?o WHERE {\n"
        "  ?s ?p ?o .\n"
        f"  FILTER(REGEX(STR(?s), \"{pattern}\", \"i\") || REGEX(STR(?o), \"{pattern}\", \"i\"))\n"
        "} LIMIT " + str(limit)
    )


def _build_plan(parse: QuestionParse, graph: Graph | None, *, template_id: str, expansion_purpose: str, incoming: bool = False, literal_bias: bool = False) -> QueryPlan:
    tokens = parse.anchor_candidates[:4] or parse.qualifiers[:4] or ["manual"]
    candidate_query = build_candidate_query(tokens)
    candidate_uris = rerank_candidate_uris(select_candidate_uris(graph, tokens), parse, limit=8)
    queries: list[QueryStep] = [QueryStep("candidate", "candidate_retrieval", candidate_query)]
    expansion_query = None
    fallback_used = False
    if candidate_uris:
        expansion_query = build_expansion_query(candidate_uris, incoming=incoming, limit=25 if literal_bias else 35)
        queries.append(QueryStep("expansion", expansion_purpose, expansion_query))
        sparql = expansion_query
    else:
        sparql = _build_fallback_query(tokens + parse.qualifiers, limit=20 if literal_bias else 25)
        queries.append(QueryStep("fallback", "generic_fallback", sparql))
        fallback_used = True
    return QueryPlan(
        intent=parse.intent,
        anchor_text=parse.anchor_text,
        anchor_candidates=parse.anchor_candidates,
        template_id=template_id,
        sparql=sparql,
        fallback_used=fallback_used,
        candidate_query=candidate_query,
        expansion_query=expansion_query,
        queries=queries,
        debug={"qualifiers": parse.qualifiers, "candidate_uris": candidate_uris},
    )


def template_literal_lookup(parse: QuestionParse, graph: Graph | None) -> QueryPlan:
    return _build_plan(parse, graph, template_id="T1_literal_anchor", expansion_purpose="targeted_literal_expansion", incoming=False, literal_bias=True)


def template_reference_lookup(parse: QuestionParse, graph: Graph | None) -> QueryPlan:
    return _build_plan(parse, graph, template_id="T2_reference_lookup", expansion_purpose="incoming_reference_expansion", incoming=True)


def template_regulatory_lookup(parse: QuestionParse, graph: Graph | None) -> QueryPlan:
    return _build_plan(parse, graph, template_id="T3_regulatory_lookup", expansion_purpose="regulatory_expansion", incoming=False)


def template_component_attribute_lookup(parse: QuestionParse, graph: Graph | None) -> QueryPlan:
    return _build_plan(parse, graph, template_id="T4_component_attribute_lookup", expansion_purpose="component_attribute_expansion", incoming=False)


def template_component_relation_lookup(parse: QuestionParse, graph: Graph | None) -> QueryPlan:
    return _build_plan(parse, graph, template_id="T5_component_relation_lookup", expansion_purpose="relation_expansion", incoming=False)


def template_purpose_lookup(parse: QuestionParse, graph: Graph | None) -> QueryPlan:
    return _build_plan(parse, graph, template_id="T6_purpose_lookup", expansion_purpose="purpose_expansion", incoming=False)


TEMPLATE_BUILDERS: dict[str, Callable[[QuestionParse, Graph | None], QueryPlan]] = {
    "literal_lookup": template_literal_lookup,
    "figure_or_reference_lookup": template_reference_lookup,
    "regulatory_lookup": template_regulatory_lookup,
    "component_attribute_lookup": template_component_attribute_lookup,
    "component_relation_lookup": template_component_relation_lookup,
    "purpose_or_function_lookup": template_purpose_lookup,
}


def build_query_plan(question: str, schema_text: str, graph: Graph | None = None) -> QueryPlan:
    parse = build_question_parse(question)
    builder = TEMPLATE_BUILDERS.get(parse.intent, template_literal_lookup)
    plan = builder(parse, graph)
    plan.debug.update({
        "schema_excerpt_used": bool(schema_text),
        "question_parse": asdict(parse),
    })
    return plan


def execute_query_plan(plan: QueryPlan, graph: Graph) -> QueryExecutionResult:
    rows: list[tuple[str, str, str]] = []
    raw_bindings: list[tuple[str, str, str]] = []
    seen = set()
    executable_steps = [
        step for step in (plan.queries or [QueryStep("single", "single_query", plan.sparql)])
        if step.step_id != "candidate"
    ]
    for step in executable_steps:
        query_text = step.sparql
        try:
            for row in graph.query(query_text):
                values = tuple(str(value) for value in row)
                if values in seen:
                    continue
                seen.add(values)
                raw_bindings.append(values)
                if len(values) == 3:
                    rows.append((normalize_uri(values[0]), normalize_uri(values[1]), normalize_uri(values[2])))
                elif len(values) == 2:
                    rows.append((normalize_uri(values[0]), step.step_id, normalize_uri(values[1])))
                elif len(values) == 1:
                    rows.append((normalize_uri(values[0]), step.step_id, ""))
        except Exception:
            continue
    plan.debug["candidate_count"] = len(plan.debug.get("candidate_uris", []))
    plan.debug["result_count"] = len(rows)
    return QueryExecutionResult(plan=plan, rows=rows, raw_bindings=raw_bindings)


def append_query_debug_record(record: dict[str, object], path: Path = QUERY_DEBUG_REPORT_PATH) -> None:
    payload = []
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = []
    payload.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def export_intent_catalog_from_dataset(dataset_path: Path, output_path: Path = QUERY_INTENT_CATALOG_PATH) -> dict[str, object]:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    intents = []
    qid = 1
    for block_index, block in enumerate(payload):
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


def main() -> None:
    args = parse_args()
    graph = cargar_grafo_memoria()
    plan = build_query_plan(args.question, schema_text="", graph=graph)
    result = execute_query_plan(plan, graph)
    print(json.dumps({
        "query_plan": asdict(plan),
        "result_count": len(result.rows),
        "sample_rows": result.rows[:10],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
