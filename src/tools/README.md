# src/tools

Standalone repair and maintenance utilities. These scripts operate on existing pipeline artifacts and are not invoked by the main pipeline entrypoints.

## materialize_inverses.py

Reads all `owl:inverseOf` pairs from the operational T-Box and materializes the missing inverse triples in `abox_linked.ttl`. Republishes the updated A-Box to GraphDB.

Use after any rebuild in which the link completer does not propagate inverse triples (expected: the link completer applies only 7 hardcoded family rules, not generic inverseOf closure).

```bash
python src/tools/materialize_inverses.py
```

Inputs: `data/processed/ontology_aligned.ttl`, `data/processed/abox_linked.ttl`
Output: updated `data/processed/abox_linked.ttl`, GraphDB republished
