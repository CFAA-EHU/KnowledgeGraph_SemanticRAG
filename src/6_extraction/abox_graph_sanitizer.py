from __future__ import annotations

import json
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from artifact_contracts import ABOX_MINTED_ENTITY_REGISTRY_PATH

EX = Namespace("https://vocab.cfaa.eus/broaching/")
BASE_URI = str(EX)
SURFACE_PREDICATES = (RDFS.label, EX.identificador, EX.textoExtracto)
LOCAL_NAME_MAX_LENGTH = 80
GENERIC_SURFACES = {
    "accion",
    "accionprohibida",
    "alarma",
    "almacen",
    "aviso",
    "avisoseguridad",
    "canal",
    "componente",
    "comando",
    "diagnostico",
    "diagnosticofallo",
    "encoder",
    "funcion",
    "herramienta",
    "interfazusuario",
    "marca",
    "motor",
    "pagina",
    "palpador",
    "parametro",
    "sensor",
    "sub",
    "tarea",
    "tareamantenimiento",
    "tmoperation",
}


@dataclass
class SanitizationResult:
    minted_nodes: int = 0
    reused_registry_iris: int = 0
    replaced_file_iris: int = 0
    purged_file_iris: int = 0
    redundant_type_triples_removed: int = 0
    inferred_missing_types: int = 0
    invalid_hex_binary_literals_downgraded: int = 0
    texto_extracto_removed: int = 0
    texto_extracto_trimmed: int = 0
    texto_extracto_added_from_traceability: int = 0
    incidental_table_types_removed: int = 0
    type_object_minting_prevented: int = 0
    long_local_name_truncated: int = 0
    hash_due_to_weak_identity: int = 0
    hash_due_to_collision: int = 0
    phrase_like_entities_purged: int = 0
    minted_assignments: dict[str, str] = field(default_factory=dict)
    purged_nodes: list[str] = field(default_factory=list)

    def to_manifest_summary(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["purged_nodes"] = self.purged_nodes[:20]
        payload["minted_assignments"] = dict(list(self.minted_assignments.items())[:20])
        return payload


def load_mint_registry(path: Path = ABOX_MINTED_ENTITY_REGISTRY_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    mappings = payload.get("mappings", payload if isinstance(payload, dict) else {})
    if not isinstance(mappings, dict):
        return {}
    return {str(key): str(value) for key, value in mappings.items()}


def save_mint_registry(registry: dict[str, str], path: Path = ABOX_MINTED_ENTITY_REGISTRY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "mappings": dict(sorted(registry.items())),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def serialize_graph(graph: Graph) -> str:
    return graph.serialize(format="turtle")


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _to_camel_case(text: str) -> str:
    normalized = _strip_accents(text)
    normalized = re.sub(r"[^A-Za-z0-9]+", " ", normalized)
    parts = [part for part in normalized.split() if part]
    if not parts:
        return ""
    local_name = "".join(part[:1].upper() + part[1:] for part in parts)
    if local_name and local_name[0].isdigit():
        local_name = f"Entity{local_name}"
    return local_name


def _short_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:10]


def _uuid_suffix(value: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, value).hex[:10]


def _normalize_surface_for_key(value: str) -> str:
    return _normalize_text(value).replace(" ", "_")


def _entity_surfaces(graph: Graph, node: BNode | URIRef) -> dict[str, list[str]]:
    labels = [str(obj) for obj in graph.objects(node, RDFS.label) if isinstance(obj, Literal)]
    identifiers = [str(obj) for obj in graph.objects(node, EX.identificador) if isinstance(obj, Literal)]
    extracts = [str(obj) for obj in graph.objects(node, EX.textoExtracto) if isinstance(obj, Literal)]
    return {
        "labels": labels,
        "identifiers": identifiers,
        "texto_extractos": extracts,
    }


def _node_types(graph: Graph, node: BNode | URIRef) -> list[str]:
    return sorted(str(obj) for obj in graph.objects(node, RDF.type) if isinstance(obj, URIRef))


def _domain_like(graph: Graph, node: BNode | URIRef) -> bool:
    if any(True for _ in graph.objects(node, RDF.type)):
        return True
    if any(True for predicate in SURFACE_PREDICATES for _ in graph.objects(node, predicate)):
        return True
    return False


def _preferred_surface(graph: Graph, node: BNode | URIRef) -> tuple[str | None, str | None]:
    surfaces = _entity_surfaces(graph, node)
    if surfaces["labels"]:
        return surfaces["labels"][0], "label"
    if surfaces["identifiers"]:
        return surfaces["identifiers"][0], "identificador"
    return None, None


def _preferred_type_local_name(graph: Graph, node: BNode | URIRef) -> str:
    types = _node_types(graph, node)
    if not types:
        return "Entidad"
    return max((uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1] for uri in types), key=len)


def _is_generic_surface(surface: str | None) -> bool:
    if not surface:
        return True
    normalized_words = _normalize_text(surface).split()
    normalized = "".join(normalized_words)
    normalized_without_digits = re.sub(r"\d+", "", normalized)
    first_word = normalized_words[0] if normalized_words else ""
    if normalized in GENERIC_SURFACES:
        return True
    if normalized_without_digits in GENERIC_SURFACES:
        return True
    if first_word in GENERIC_SURFACES:
        return True
    return len(normalized_words) < 2


def _looks_code_like_surface(surface: str | None) -> bool:
    if not surface:
        return False
    compact = re.sub(r"\s+", "", surface)
    return bool(re.fullmatch(r"[A-Z0-9_#.\-\[\]=]+", compact))


def _local_name_to_surface(local_name: str) -> str:
    local_name = re.sub(r"_+", " ", local_name)
    local_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", local_name)
    return local_name.strip()


def _local_name_to_phrase_key(local_name: str) -> str:
    """Normalize local names for phrase-entity detection.

    This intentionally compares compact keys because LLM-generated IRIs often
    collapse a leading article/preposition into the first token, e.g.
    AContinuacion -> "a continuacion".
    """
    return _normalize_text(_local_name_to_surface(local_name)).replace(" ", "")


def _surface_is_numeric_variant(surface: str | None) -> bool:
    if not surface:
        return False
    words = _normalize_text(surface).split()
    return len(words) >= 2 and words[-1].isdigit()


def _should_remint_existing_uri(graph: Graph, node: URIRef) -> bool:
    node_str = str(node)
    if not node_str.startswith(BASE_URI):
        return False
    preferred_surface, source = _preferred_surface(graph, node)
    surfaces = _entity_surfaces(graph, node)
    local_name = node_str.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    local_surface = _local_name_to_surface(local_name)
    if source == "identificador" and _looks_code_like_surface(preferred_surface):
        return True
    if _surface_is_numeric_variant(preferred_surface):
        return True
    if _is_generic_surface(local_surface):
        if surfaces["identifiers"]:
            return True
        if source in {"identificador", "textoExtracto"}:
            return True
        if _surface_is_numeric_variant(preferred_surface):
            return True
        if preferred_surface and _normalize_text(preferred_surface) != _normalize_text(local_surface):
            return True
    if _is_generic_surface(preferred_surface) and source == "identificador":
        return True
    return False


def _best_context_value(graph: Graph, node: BNode | URIRef) -> str:
    surfaces = _entity_surfaces(graph, node)
    if surfaces["identifiers"]:
        return surfaces["identifiers"][0]
    if surfaces["texto_extractos"]:
        fragments = sorted(surfaces["texto_extractos"], key=len)
        return fragments[0][:120]
    triples = []
    for _, predicate, obj in graph.triples((node, None, None)):
        predicate_name = str(predicate).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        object_value = str(obj)
        triples.append(f"{predicate_name}={object_value}")
    return "|".join(sorted(triples))


def _limit_local_name(local_name: str, key: str) -> tuple[str, bool]:
    if len(local_name) <= LOCAL_NAME_MAX_LENGTH:
        return local_name, False
    hash_suffix = _short_hash(key)
    prefix_length = LOCAL_NAME_MAX_LENGTH - len(hash_suffix) - 1
    return f"{local_name[:prefix_length].rstrip('_')}_{hash_suffix}", True


def _build_mint_key(graph: Graph, node: BNode | URIRef) -> tuple[str, str, bool, bool]:
    preferred_type = _preferred_type_local_name(graph, node)
    preferred_surface, _source = _preferred_surface(graph, node)
    context_value = _best_context_value(graph, node)
    weak_identity = not preferred_surface or _is_generic_surface(preferred_surface)

    if not weak_identity:
        surface_component = _normalize_surface_for_key(preferred_surface or preferred_type)
        key = f"{preferred_type.lower()}|{surface_component or preferred_type.lower()}"
        if context_value and context_value != preferred_surface:
            key = f"{key}|{_normalize_surface_for_key(context_value)[:80] or _short_hash(context_value)}"
        base_local_name = _to_camel_case(preferred_surface or preferred_type) or _to_camel_case(preferred_type) or "Entidad"
    else:
        context_component = _normalize_surface_for_key(context_value) or _short_hash(context_value or preferred_type)
        key = f"{preferred_type.lower()}|{context_component}"
        base_local_name = _to_camel_case(preferred_type) or "Entidad"
        base_local_name = f"{base_local_name}_{_short_hash(key)}"

    base_local_name, truncated = _limit_local_name(base_local_name, key)
    return key, base_local_name, weak_identity, truncated


def _mint_uri_for_key(
    key: str,
    base_local_name: str,
    *,
    registry: dict[str, str],
    occupied_uris: set[str],
) -> tuple[str, bool, bool]:
    existing = registry.get(key)
    if existing:
        occupied_uris.add(existing)
        return existing, True, False

    candidate = f"{BASE_URI}{base_local_name}"
    collision_hashed = False
    if candidate in occupied_uris:
        candidate = f"{BASE_URI}{base_local_name}_{_short_hash(key)}"
        collision_hashed = True
    if candidate in occupied_uris:
        candidate = f"{BASE_URI}{base_local_name}_{_uuid_suffix(key)}"
        collision_hashed = True

    registry[key] = candidate
    occupied_uris.add(candidate)
    return candidate, False, collision_hashed


def downgrade_invalid_hex_binary_literals(graph: Graph, *, result: SanitizationResult | None = None) -> Graph:
    result = result or SanitizationResult()
    replacements: list[tuple[URIRef | BNode, URIRef, Literal, Literal]] = []

    for subject, predicate, obj in graph:
        if not isinstance(obj, Literal):
            continue
        if obj.datatype != XSD.hexBinary:
            continue
        lexical = str(obj).strip()
        if _is_valid_hex_binary_lexical(lexical):
            continue
        replacements.append((subject, predicate, obj, Literal(lexical, datatype=XSD.string)))

    for subject, predicate, old_literal, new_literal in replacements:
        graph.remove((subject, predicate, old_literal))
        graph.add((subject, predicate, new_literal))

    result.invalid_hex_binary_literals_downgraded += len(replacements)
    return graph


def mint_domain_iris_for_anonymous_nodes(
    graph: Graph,
    *,
    mint_registry: dict[str, str] | None = None,
    result: SanitizationResult | None = None,
) -> Graph:
    mint_registry = mint_registry if mint_registry is not None else {}
    result = result or SanitizationResult()
    occupied_uris = {str(subject) for subject in graph.subjects() if isinstance(subject, URIRef)}
    occupied_uris |= {str(obj) for obj in graph.objects() if isinstance(obj, URIRef)}
    occupied_uris |= set(mint_registry.values())

    mapping: dict[BNode | URIRef, URIRef] = {}
    nodes_to_purge: set[BNode | URIRef] = set()
    candidate_nodes: set[BNode | URIRef] = set()

    for subject, predicate, obj in graph:
        if isinstance(subject, (BNode, URIRef)):
            if isinstance(subject, BNode) or (
                isinstance(subject, URIRef)
                and (str(subject).startswith("file:///") or _should_remint_existing_uri(graph, subject))
            ):
                candidate_nodes.add(subject)
        if predicate == RDF.type:
            result.type_object_minting_prevented += 1
            if isinstance(obj, (BNode, URIRef)) and (
                isinstance(obj, BNode)
                or str(obj).startswith("file:///")
                or (isinstance(obj, URIRef) and _should_remint_existing_uri(graph, obj))
            ):
                # The counter above tracks all protected rdf:type objects; this
                # branch documents the cases that would otherwise be candidates.
                pass
            continue
        if isinstance(obj, (BNode, URIRef)):
            if isinstance(obj, BNode) or (
                isinstance(obj, URIRef)
                and (str(obj).startswith("file:///") or _should_remint_existing_uri(graph, obj))
            ):
                candidate_nodes.add(obj)

    for node in sorted(candidate_nodes, key=str):
        if _domain_like(graph, node):
            key, base_local_name, weak_identity, truncated = _build_mint_key(graph, node)
            minted_uri, reused, collision_hashed = _mint_uri_for_key(
                key,
                base_local_name,
                registry=mint_registry,
                occupied_uris=occupied_uris,
            )
            mapping[node] = URIRef(minted_uri)
            if reused:
                result.reused_registry_iris += 1
            else:
                result.minted_nodes += 1
                if weak_identity:
                    result.hash_due_to_weak_identity += 1
                if truncated:
                    result.long_local_name_truncated += 1
                if collision_hashed:
                    result.hash_due_to_collision += 1
            if isinstance(node, URIRef) and str(node).startswith("file:///"):
                result.replaced_file_iris += 1
            result.minted_assignments[str(node)] = minted_uri
        elif isinstance(node, URIRef) and str(node).startswith("file:///"):
            nodes_to_purge.add(node)
            result.purged_file_iris += 1
            result.purged_nodes.append(str(node))

    rewritten = Graph()
    for subject, predicate, obj in graph:
        if subject in nodes_to_purge or obj in nodes_to_purge:
            continue
        new_subject = mapping.get(subject, subject)
        new_object = obj if predicate == RDF.type else mapping.get(obj, obj)
        if isinstance(new_object, URIRef) and new_subject == new_object and (new_subject != subject or new_object != obj):
            continue
        rewritten.add((new_subject, predicate, new_object))
    return rewritten


def _build_subclass_closure(tbox_graph: Graph) -> dict[str, set[str]]:
    parents: dict[str, set[str]] = {}
    for child, _, parent in tbox_graph.triples((None, RDFS.subClassOf, None)):
        if isinstance(child, URIRef) and isinstance(parent, URIRef):
            parents.setdefault(str(child), set()).add(str(parent))

    closure: dict[str, set[str]] = {}

    def visit(uri: str, seen: set[str] | None = None) -> set[str]:
        if uri in closure:
            return closure[uri]
        seen = seen or set()
        if uri in seen:
            return set()
        seen.add(uri)
        ancestors = set(parents.get(uri, set()))
        for parent_uri in list(ancestors):
            ancestors |= visit(parent_uri, seen)
        closure[uri] = ancestors
        return ancestors

    for uri in parents:
        visit(uri)
    return closure


def _load_tbox_domains(tbox_graph: Graph) -> dict[URIRef, set[URIRef]]:
    domains: dict[URIRef, set[URIRef]] = {}
    for predicate, _, domain in tbox_graph.triples((None, RDFS.domain, None)):
        if isinstance(predicate, URIRef) and isinstance(domain, URIRef) and str(domain) != str(URIRef("http://www.w3.org/2002/07/owl#Thing")):
            domains.setdefault(predicate, set()).add(domain)
    return domains


def infer_missing_types(graph: Graph, *, tbox_graph: Graph, result: SanitizationResult | None = None) -> Graph:
    result = result or SanitizationResult()
    tbox_classes = {class_uri for class_uri in tbox_graph.subjects(RDF.type, URIRef("http://www.w3.org/2002/07/owl#Class")) if isinstance(class_uri, URIRef)}
    domains = _load_tbox_domains(tbox_graph)
    additions: list[tuple[URIRef, URIRef, URIRef]] = []

    keyword_types = [
        (re.compile(r"\baccion prohibida\b|^accionprohibida", re.IGNORECASE), EX.AccionProhibida),
        (re.compile(r"\btarea mantenimiento\b|^tareamantenimiento", re.IGNORECASE), EX.TareaMantenimiento),
        (re.compile(r"\bmodo operacion\b|^modooperacion", re.IGNORECASE), EX.ModoOperacion),
        (re.compile(r"\btabla\b|^tabla", re.IGNORECASE), EX.Tabla),
        (re.compile(r"\besquema\b|^esquema", re.IGNORECASE), EX.Esquema),
        (re.compile(r"\bpanel\b|^panel", re.IGNORECASE), EX.InterfazUsuario),
        (re.compile(r"\bcontactor\b|\binterruptor\b", re.IGNORECASE), EX.ComponenteElectrico),
        (re.compile(r"\bdeposito\b|\bdep[oó]sito\b", re.IGNORECASE), EX.Sistema),
    ]

    candidate_subjects = {
        subject
        for subject in graph.subjects()
        if isinstance(subject, URIRef)
    } | {
        subject
        for subject in graph.subjects(RDFS.label, None)
        if isinstance(subject, URIRef)
    }

    for subject in sorted(candidate_subjects, key=str):
        if any(True for _ in graph.objects(subject, RDF.type)):
            continue

        inferred: URIRef | None = None
        subject_domains: set[URIRef] = set()
        for predicate, _obj in graph.predicate_objects(subject):
            subject_domains |= {domain for domain in domains.get(predicate, set()) if domain in tbox_classes}
        if len(subject_domains) == 1:
            inferred = next(iter(subject_domains))

        if inferred is None:
            local_name = _local_name_to_surface(str(subject).rsplit("/", 1)[-1].rsplit("#", 1)[-1])
            labels = " ".join(str(obj) for obj in graph.objects(subject, RDFS.label) if isinstance(obj, Literal))
            surface = f"{local_name} {labels}".strip()
            for pattern, class_uri in keyword_types:
                if class_uri in tbox_classes and pattern.search(surface):
                    inferred = class_uri
                    break

        if inferred is not None:
            additions.append((subject, RDF.type, inferred))

    for triple in additions:
        graph.add(triple)
    result.inferred_missing_types += len(additions)
    return graph


def drop_redundant_supertypes(graph: Graph, *, tbox_graph: Graph, result: SanitizationResult | None = None) -> Graph:
    result = result or SanitizationResult()
    subclass_closure = _build_subclass_closure(tbox_graph)
    redundant_triples: list[tuple[URIRef, URIRef, URIRef]] = []

    for subject in {subject for subject in graph.subjects() if isinstance(subject, URIRef)}:
        types = [obj for obj in graph.objects(subject, RDF.type) if isinstance(obj, URIRef)]
        type_uris = {str(type_uri) for type_uri in types}
        for type_uri in types:
            type_str = str(type_uri)
            if any(type_str in subclass_closure.get(other_type, set()) for other_type in type_uris if other_type != type_str):
                redundant_triples.append((subject, RDF.type, type_uri))

    for triple in redundant_triples:
        graph.remove(triple)
    result.redundant_type_triples_removed += len(redundant_triples)
    return graph


def drop_incidental_table_types(graph: Graph, *, result: SanitizationResult | None = None) -> Graph:
    result = result or SanitizationResult()
    removed = 0

    for subject in {subject for subject in graph.subjects(RDF.type, EX.Tabla) if isinstance(subject, URIRef)}:
        types = {obj for obj in graph.objects(subject, RDF.type) if isinstance(obj, URIRef)}
        if len(types) <= 1:
            continue

        labels = [str(obj) for obj in graph.objects(subject, RDFS.label) if isinstance(obj, Literal)]
        identifiers = [str(obj) for obj in graph.objects(subject, EX.identificador) if isinstance(obj, Literal)]
        surfaces = " ".join([*labels, *identifiers])
        normalized = _normalize_text(surfaces)
        local_name = subject.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        local_normalized = _normalize_text(_local_name_to_surface(local_name))

        # The extractor often tags rows or entries from tables as ex:Tabla.
        # Keep real tables, but remove the incidental table type from concrete
        # functions, parameters, modes, or macros that already have domain type.
        looks_like_real_table = normalized.startswith("tabla ") or local_normalized.startswith("tabla ")
        looks_like_table_entry = bool(
            re.search(
                r"\b(funcion|macro|parametro|modo|comando|error|alarma|aviso|marca)\b",
                normalized,
            )
        )
        if looks_like_real_table or not looks_like_table_entry:
            continue

        graph.remove((subject, RDF.type, EX.Tabla))
        removed += 1

    result.incidental_table_types_removed += removed
    return graph


def ensure_minimal_traceability(graph: Graph, *, result: SanitizationResult | None = None) -> Graph:
    result = result or SanitizationResult()
    traceability_links = {EX.documentadoEn, EX.ilustradoEn, EX.detalladoEnEsquema}
    added = 0

    for subject in {subject for subject in graph.subjects(RDF.type, None) if isinstance(subject, URIRef)}:
        if any(True for _ in graph.objects(subject, EX.textoExtracto)):
            continue
        labels = [str(obj) for obj in graph.objects(subject, RDFS.label) if isinstance(obj, Literal)]
        identifiers = [str(obj) for obj in graph.objects(subject, EX.identificador) if isinstance(obj, Literal)]
        has_traceability_link = any(True for predicate in traceability_links for _ in graph.objects(subject, predicate))
        if labels:
            graph.add((subject, EX.textoExtracto, Literal(labels[0])))
            added += 1
        elif identifiers:
            graph.add((subject, EX.textoExtracto, Literal(identifiers[0])))
            added += 1
        elif has_traceability_link:
            graph.add((subject, EX.textoExtracto, Literal("Entidad documentada por enlace de trazabilidad.")))
            added += 1

    result.texto_extracto_added_from_traceability += added
    return graph


def _surface_tokens(graph: Graph, subject: URIRef) -> set[str]:
    tokens: set[str] = set()
    for predicate in (RDFS.label, EX.identificador):
        for obj in graph.objects(subject, predicate):
            if isinstance(obj, Literal):
                tokens |= {token for token in _normalize_text(str(obj)).split() if len(token) >= 3}
    local_name = str(subject).rsplit("/", 1)[-1]
    local_name = re.sub(r"_+", " ", local_name)
    local_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", local_name)
    tokens |= {token for token in _normalize_text(local_name).split() if len(token) >= 3}
    return tokens


def _texto_extract_score(text: str, surface_tokens: set[str]) -> float:
    normalized = _normalize_text(text)
    text_tokens = {token for token in normalized.split() if len(token) >= 3}
    overlap = len(text_tokens & surface_tokens)
    score = float(overlap)
    if 8 <= len(text) <= 220:
        score += 1.0
    if len(text) <= 320:
        score += 0.5
    return score


def _literal_with_same_metadata(source: Literal, text: str) -> Literal:
    if source.language:
        return Literal(text, lang=source.language)
    if source.datatype:
        return Literal(text, datatype=source.datatype)
    return Literal(text)


def _is_valid_hex_binary_lexical(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9A-Fa-f]*", value)) and len(value) % 2 == 0


def _compact_extract_candidate(text: str, *, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    clipped = compact[:limit].rstrip(" ,;:-")
    return f"{clipped}..."


def _derive_scoped_extract(text: str, surface_tokens: set[str], *, limit: int = 220) -> str | None:
    lines = [line.strip(" |") for line in text.splitlines() if line.strip(" |-")]
    scored_lines: list[tuple[float, str]] = []
    for line in lines:
        score = _texto_extract_score(line, surface_tokens)
        if score > 0:
            scored_lines.append((score, line))

    if scored_lines:
        scored_lines.sort(key=lambda item: (-item[0], len(item[1])))
        best_line = scored_lines[0][1]
        return _compact_extract_candidate(best_line, limit=limit)

    compact = _compact_extract_candidate(text, limit=limit)
    return compact or None


def prune_or_scope_texto_extracto(
    graph: Graph,
    *,
    source_chunk_text: str | None = None,
    result: SanitizationResult | None = None,
) -> Graph:
    result = result or SanitizationResult()
    chunk_normalized = _normalize_text(source_chunk_text or "")

    for subject in {subject for subject in graph.subjects() if isinstance(subject, URIRef)}:
        extracts = [obj for obj in graph.objects(subject, EX.textoExtracto) if isinstance(obj, Literal)]
        if not extracts:
            continue

        surface_tokens = _surface_tokens(graph, subject)
        keepers: list[Literal] = []
        best_score = -1.0
        best_literal: Literal | None = None

        for literal in extracts:
            text = str(literal)
            normalized = _normalize_text(text)
            identical_to_chunk = chunk_normalized and normalized == chunk_normalized
            large_chunk_like = chunk_normalized and len(normalized) >= max(240, int(len(chunk_normalized) * 0.9))
            has_surface_overlap = bool(surface_tokens & {token for token in normalized.split() if len(token) >= 3})

            if identical_to_chunk and (large_chunk_like or not has_surface_overlap):
                scoped = _derive_scoped_extract(text, surface_tokens)
                if scoped and scoped != text:
                    replacement = _literal_with_same_metadata(literal, scoped)
                    graph.remove((subject, EX.textoExtracto, literal))
                    graph.add((subject, EX.textoExtracto, replacement))
                    result.texto_extracto_trimmed += 1
                    literal = replacement
                    text = str(literal)
                    normalized = _normalize_text(text)
                    identical_to_chunk = chunk_normalized and normalized == chunk_normalized
                    large_chunk_like = chunk_normalized and len(normalized) >= max(240, int(len(chunk_normalized) * 0.9))
                if identical_to_chunk and (large_chunk_like or not has_surface_overlap):
                    result.texto_extracto_removed += 1
                    continue
            if len(text) > 400 and not has_surface_overlap:
                result.texto_extracto_removed += 1
                continue

            score = _texto_extract_score(text, surface_tokens)
            if score > best_score:
                best_score = score
                best_literal = literal

        if best_literal is not None:
            keepers = [best_literal]

        for literal in extracts:
            if literal not in keepers:
                graph.remove((subject, EX.textoExtracto, literal))
                result.texto_extracto_removed += 1

        if keepers and len(extracts) > 1:
            result.texto_extracto_trimmed += len(extracts) - 1

    return graph


def purge_phrase_like_entities(graph: Graph, *, result: SanitizationResult | None = None) -> Graph:
    """Remove obvious sentence-as-entity artifacts.

    The extractor can occasionally turn a full narrative sentence into a
    domain individual. We only purge when the node has no strong identity,
    no incoming references, and its local name is effectively the same as its
    textual extract. This keeps the rule safe for existing named assets.
    """
    result = result or SanitizationResult()
    nodes_to_purge: set[URIRef] = set()

    for subject in {s for s in graph.subjects(RDF.type, None) if isinstance(s, URIRef)}:
        subject_str = str(subject)
        if not subject_str.startswith(BASE_URI):
            continue
        if any(True for _ in graph.objects(subject, RDFS.label)):
            continue
        if any(True for _ in graph.objects(subject, EX.identificador)):
            continue
        if any(True for _ in graph.triples((None, None, subject))):
            continue

        local_name = subject_str.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        local_words = _normalize_text(_local_name_to_surface(local_name)).split()
        if len(local_words) < 8:
            continue
        if _looks_code_like_surface(local_name):
            continue

        local_key = _local_name_to_phrase_key(local_name)
        extracts = [str(obj) for obj in graph.objects(subject, EX.textoExtracto) if isinstance(obj, Literal)]
        if not extracts:
            continue
        for extract in extracts:
            extract_key = _normalize_text(extract).replace(" ", "")
            if local_key and extract_key and (local_key == extract_key or local_key in extract_key or extract_key in local_key):
                nodes_to_purge.add(subject)
                break

    if not nodes_to_purge:
        return graph

    rewritten = Graph()
    for subject, predicate, obj in graph:
        if subject in nodes_to_purge or obj in nodes_to_purge:
            continue
        rewritten.add((subject, predicate, obj))

    result.phrase_like_entities_purged += len(nodes_to_purge)
    result.purged_nodes.extend(str(node) for node in sorted(nodes_to_purge, key=str))
    return rewritten


def sanitize_abox_graph(
    graph: Graph,
    *,
    tbox_graph: Graph,
    source_chunk_text: str | None = None,
    mint_registry: dict[str, str] | None = None,
) -> tuple[Graph, SanitizationResult]:
    result = SanitizationResult()
    sanitized = mint_domain_iris_for_anonymous_nodes(
        graph,
        mint_registry=mint_registry,
        result=result,
    )
    sanitized = downgrade_invalid_hex_binary_literals(sanitized, result=result)
    sanitized = infer_missing_types(sanitized, tbox_graph=tbox_graph, result=result)
    sanitized = drop_redundant_supertypes(sanitized, tbox_graph=tbox_graph, result=result)
    sanitized = drop_incidental_table_types(sanitized, result=result)
    sanitized = ensure_minimal_traceability(sanitized, result=result)
    sanitized = prune_or_scope_texto_extracto(
        sanitized,
        source_chunk_text=source_chunk_text,
        result=result,
    )
    sanitized = purge_phrase_like_entities(sanitized, result=result)
    return sanitized, result
