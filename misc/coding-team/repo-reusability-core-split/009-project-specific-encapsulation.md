# Context

Once historical tooling is isolated, T27B should make the project-specific boundary more visible without turning the repo into a disruptive structural refactor.

# Objective

Encapsulate the most obvious project-specific assets and boundaries so the reusable core is clearer and the later split to a broaching-specific repository is easier.

# Scope

- Use the structural isolation candidate report as the source of truth.
- Apply only low-risk changes that make project-specific boundaries explicit, such as:
  - introducing or documenting a project-specific grouping area
  - isolating clearly project-bound manifests, datasets, or reports where safe
  - making future-split candidates more visible without breaking current rebuildability
- Update references only as needed to preserve compatibility.

# Non-goals / Later

- Do not extract the project to a new repository yet.
- Do not move runtime contract artifacts out of their current operational locations if that would break the rebuild path.
- Do not refactor retrieval/planner semantics.

# Constraints / Caveats

- Keep the accepted project corpus rebuildable from this repository.
- Avoid moves that would force broad path rewrites across the runtime.
- If an asset is too risky to move now, classify and document it rather than forcing the move.

# Acceptance Notes

- After this task, the repository should expose a clearer visual and contractual distinction between reusable runtime core and project-specific assets.
