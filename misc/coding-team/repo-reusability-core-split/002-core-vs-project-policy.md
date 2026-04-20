# Context

After the inventory, T27A needs a formal policy that defines what remains part of the reusable repository core and what is specific to the current broaching/CNC project.

# Objective

Define the explicit `core vs project` policy for the repository and persist it as `data/processed/t27_core_vs_project_policy.json`.

# Scope

- Use the inventory as the source of classification context.
- Define:
  - `core_modules`
  - `project_specific_modules`
  - `historical_wrappers`
  - `stable_entrypoints`
  - `runtime_contract_artifacts`
  - `future_project_repo_candidates`
  - `archival_policy`
- Make explicit that current accepted-manual assets and golden sets are project-specific even if retained in-repo.

# Non-goals / Later

- Do not move files yet.
- Do not archive anything yet.
- Do not create the new project repository.

# Constraints / Caveats

- Policy must preserve compatibility with the current runtime.
- Do not label historical or diagnostic tooling as operational primary path.
- Include the rule: `historical_tooling_declassified_from_operational_path = true`.

# Acceptance Notes

- The policy should be strong enough that a new engineer can tell what the reusable framework is without inferring intent from historical reports.
