#!/usr/bin/env python3
"""
Valida la coherencia semántica de las relaciones en los TTL mergeados
contra el T-Box operacional.

Ejecutar:
  mi-entorno/bin/python3 src/6_extraction/relation_validator.py \
    [--tbox data/processed/ontology_aligned.ttl] \
    [--abox data/processed/a218_merged.ttl data/processed/variables_cnc_merged.ttl ...]
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, OWL, RDF, RDFS, URIRef, Literal

BASE_URI = "https://vocab.cfaa.eus/broaching/"
REPO_ROOT = Path(__file__).resolve().parents[2]


# ── helpers ──────────────────────────────────────────────────────────────────

def local(uri) -> str:
    return str(uri).split("/")[-1] if "/" in str(uri) else str(uri).split("#")[-1]


def load_tbox(path: Path):
    """Devuelve (graph, domains, ranges, inverse_of, obj_props, data_props, classes, subclass_map).

    subclass_map[C] = conjunto transitivo de superclases de C (incluyendo C mismo).
    Permite validación OWL-aware: si domain(p) = {EntidadFisica} y sujeto es Sistema,
    la validación pasa porque Sistema ⊑ EntidadFisica.
    """
    g = Graph()
    g.parse(path, format="turtle")

    domains: dict[str, set[str]] = defaultdict(set)
    ranges: dict[str, set[str]] = defaultdict(set)
    inverse_of: dict[str, str] = {}
    obj_props: set[str] = set()
    data_props: set[str] = set()
    classes: set[str] = set()
    direct_superclasses: dict[str, set[str]] = defaultdict(set)

    for s, _, o in g.triples((None, RDF.type, OWL.ObjectProperty)):
        obj_props.add(local(s))
    for s, _, o in g.triples((None, RDF.type, OWL.DatatypeProperty)):
        data_props.add(local(s))
    for s, _, o in g.triples((None, RDF.type, OWL.Class)):
        classes.add(local(s))
    for s, _, o in g.triples((None, RDFS.subClassOf, None)):
        direct_superclasses[local(s)].add(local(o))

    for s, _, o in g.triples((None, RDFS.domain, None)):
        domains[local(s)].add(local(o))
    for s, _, o in g.triples((None, RDFS.range, None)):
        ranges[local(s)].add(local(o))
    for s, _, o in g.triples((None, OWL.inverseOf, None)):
        inverse_of[local(s)] = local(o)
        inverse_of[local(o)] = local(s)

    # Construir cierre transitivo de superclases para cada clase
    def ancestors(cls: str, visited: set | None = None) -> set[str]:
        if visited is None:
            visited = set()
        if cls in visited:
            return visited
        visited.add(cls)
        for sup in direct_superclasses.get(cls, set()):
            ancestors(sup, visited)
        return visited

    subclass_map: dict[str, set[str]] = {}
    for cls in classes | {"owl#Thing", "Thing"}:
        subclass_map[cls] = ancestors(cls)
        subclass_map[cls].add("owl#Thing")  # owl:Thing es superclase de todo

    return g, domains, ranges, inverse_of, obj_props, data_props, classes, subclass_map


def load_abox(paths: list[Path]) -> Graph:
    g = Graph()
    for p in paths:
        g.parse(p, format="turtle")
    return g


def get_types(abox: Graph, node: URIRef) -> set[str]:
    return {local(o) for _, _, o in abox.triples((node, RDF.type, None))}


# ── análisis ─────────────────────────────────────────────────────────────────

def type_satisfies(node_types: set[str], allowed: set[str], subclass_map: dict) -> bool:
    """True si algún tipo del nodo es subclase de alguna clase permitida (OWL reasoning)."""
    if not allowed or "owl#Thing" in allowed or "Thing" in allowed:
        return True
    for t in node_types:
        ancestors = subclass_map.get(t, {t})
        if ancestors & allowed:
            return True
    return False


def analyse(tbox_path: Path, abox_paths: list[Path]) -> dict:
    print(f"Cargando T-Box: {tbox_path.name}")
    _, domains, ranges, inverse_of, obj_props, data_props, classes, subclass_map = load_tbox(tbox_path)
    tbox_props = obj_props | data_props

    print(f"Cargando {len(abox_paths)} A-Box(es)...")
    abox = load_abox(abox_paths)
    print(f"  → {len(abox)} tripletas totales")

    # ── 1. Recuento de uso por predicado ────────────────────────────────────
    pred_count: dict[str, int] = defaultdict(int)
    pred_subj_types: dict[str, defaultdict] = defaultdict(lambda: defaultdict(int))
    pred_obj_types: dict[str, defaultdict] = defaultdict(lambda: defaultdict(int))

    for s, p, o in abox:
        if str(p).startswith("http://www.w3.org/"):
            continue  # skip rdf/rdfs/owl built-ins
        pred = local(p)
        pred_count[pred] += 1
        for t in get_types(abox, s):
            pred_subj_types[pred][t] += 1
        if isinstance(o, URIRef):
            for t in get_types(abox, o):
                pred_obj_types[pred][t] += 1
        else:
            pred_obj_types[pred]["Literal"] += 1

    # ── 2. Propiedades huérfanas (A-Box usa, T-Box no conoce) ──────────────
    abox_only = {p for p in pred_count if p not in tbox_props and p not in ("type",)}
    tbox_only = {p for p in tbox_props if p not in pred_count}

    # ── 3. Violaciones domain/range ─────────────────────────────────────────
    violations: dict[str, list[dict]] = defaultdict(list)

    for s, p, o in abox:
        if str(p).startswith("http://www.w3.org/"):
            continue
        pred = local(p)
        if pred not in tbox_props:
            continue
        subj_types = get_types(abox, s)
        allowed_domains = domains.get(pred, set())
        allowed_ranges = ranges.get(pred, set())

        domain_ok = type_satisfies(subj_types, allowed_domains, subclass_map)
        if isinstance(o, URIRef):
            obj_types = get_types(abox, o)
            range_ok = type_satisfies(obj_types, allowed_ranges, subclass_map)
        else:
            range_ok = "XMLSchema#string" in allowed_ranges or not allowed_ranges

        if not domain_ok or not range_ok:
            violations[pred].append({
                "s": local(s),
                "s_types": list(subj_types),
                "p": pred,
                "o": local(o) if isinstance(o, URIRef) else str(o)[:60],
                "o_types": list(get_types(abox, o)) if isinstance(o, URIRef) else ["Literal"],
                "expected_domain": list(allowed_domains),
                "expected_range": list(allowed_ranges),
                "domain_ok": domain_ok,
                "range_ok": range_ok,
            })

    # ── 4. Asimetría de inversas ─────────────────────────────────────────────
    inverse_asymmetry: list[dict] = []
    for prop, inv_prop in inverse_of.items():
        c_prop = pred_count.get(prop, 0)
        c_inv = pred_count.get(inv_prop, 0)
        if c_prop > 0 or c_inv > 0:
            ratio = max(c_prop, c_inv) / max(min(c_prop, c_inv), 1)
            if ratio > 3 or (c_prop == 0) != (c_inv == 0):
                inverse_asymmetry.append({
                    "prop": prop, "count": c_prop,
                    "inverse": inv_prop, "inv_count": c_inv,
                    "ratio": round(ratio, 1),
                })

    return {
        "pred_count": dict(sorted(pred_count.items(), key=lambda x: -x[1])),
        "pred_subj_types": {k: dict(v) for k, v in pred_subj_types.items()},
        "pred_obj_types": {k: dict(v) for k, v in pred_obj_types.items()},
        "abox_only_predicates": sorted(abox_only),
        "tbox_only_predicates": sorted(tbox_only),
        "violations": {k: v[:10] for k, v in violations.items()},  # max 10 muestras
        "violation_counts": {k: len(v) for k, v in violations.items()},
        "inverse_asymmetry": inverse_asymmetry,
        "tbox_props": sorted(tbox_props),
        "classes": sorted(classes),
    }


# ── reporte ───────────────────────────────────────────────────────────────────

def print_report(r: dict) -> None:
    SEP = "─" * 72

    print(f"\n{SEP}")
    print("1. USO DE PREDICADOS")
    print(SEP)
    for pred, count in r["pred_count"].items():
        s_types = ", ".join(sorted(r["pred_subj_types"].get(pred, {}).keys())[:4])
        o_types = ", ".join(sorted(r["pred_obj_types"].get(pred, {}).keys())[:4])
        marker = "  ✗ " if pred in r["abox_only_predicates"] else "    "
        print(f"{marker}{pred:<30} {count:>5}   S:[{s_types}]  →  O:[{o_types}]")

    print(f"\n{SEP}")
    print("2. PREDICADOS HUÉRFANOS (A-Box usa, T-Box NO declara)")
    print(SEP)
    if r["abox_only_predicates"]:
        for p in r["abox_only_predicates"]:
            print(f"  ✗ {p}  (usos: {r['pred_count'].get(p, 0)})")
    else:
        print("  Ninguno — todo predicado usado existe en el T-Box ✓")

    print(f"\n{SEP}")
    print("3. PREDICADOS MUERTOS (T-Box declara, A-Box NUNCA usa)")
    print(SEP)
    if r["tbox_only_predicates"]:
        for p in r["tbox_only_predicates"]:
            print(f"  –  {p}")
    else:
        print("  Ninguno")

    print(f"\n{SEP}")
    print("4. VIOLACIONES DOMAIN / RANGE")
    print(SEP)
    if not r["violation_counts"]:
        print("  Sin violaciones ✓")
    else:
        for pred, count in sorted(r["violation_counts"].items(), key=lambda x: -x[1]):
            print(f"\n  [{count} violaciones]  {pred}")
            for v in r["violations"][pred][:5]:
                d_ok = "✓" if v["domain_ok"] else "✗"
                r_ok = "✓" if v["range_ok"] else "✗"
                print(f"    dom{d_ok} rng{r_ok}  {v['s']} ({','.join(v['s_types'][:2])}) "
                      f"→ {v['o']} ({','.join(v['o_types'][:2])})")
                if not v["domain_ok"]:
                    print(f"         esperado domain: {v['expected_domain']}  "
                          f"encontrado: {v['s_types']}")
                if not v["range_ok"]:
                    print(f"         esperado range:  {v['expected_range']}  "
                          f"encontrado: {v['o_types']}")

    print(f"\n{SEP}")
    print("5. ASIMETRÍA DE INVERSAS")
    print(SEP)
    if not r["inverse_asymmetry"]:
        print("  Todas las inversas se usan simétricamente ✓")
    else:
        for a in sorted(r["inverse_asymmetry"], key=lambda x: -x["ratio"]):
            print(f"  {a['prop']} ({a['count']}) ↔ {a['inverse']} ({a['inv_count']})  "
                  f"ratio={a['ratio']}x")

    print(f"\n{SEP}")
    print("RESUMEN")
    print(SEP)
    print(f"  Predicados en A-Box:          {len(r['pred_count'])}")
    print(f"  Predicados en T-Box:          {len(r['tbox_props'])}")
    print(f"  Huérfanos (solo A-Box):       {len(r['abox_only_predicates'])}")
    print(f"  Muertos   (solo T-Box):       {len(r['tbox_only_predicates'])}")
    total_viol = sum(r["violation_counts"].values())
    print(f"  Violaciones domain/range:     {total_viol}")
    print(f"  Pares de inversas asimétricos:{len(r['inverse_asymmetry'])}")
    print()


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Valida relaciones A-Box contra T-Box")
    parser.add_argument("--tbox", type=Path,
                        default=REPO_ROOT / "data/processed/ontology_aligned.ttl")
    parser.add_argument("--abox", type=Path, nargs="+",
                        default=[
                            REPO_ROOT / "data/processed/a218_merged.ttl",
                            REPO_ROOT / "data/processed/variables_cnc_merged.ttl",
                        ])
    parser.add_argument("--json-out", type=Path, default=None,
                        help="Ruta opcional para guardar reporte JSON")
    args = parser.parse_args()

    missing = [p for p in [args.tbox] + args.abox if not p.exists()]
    if missing:
        print(f"ERROR: archivos no encontrados: {missing}", file=sys.stderr)
        sys.exit(1)

    result = analyse(args.tbox, args.abox)
    print_report(result)

    if args.json_out:
        args.json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"Reporte JSON guardado en: {args.json_out}")


if __name__ == "__main__":
    main()
