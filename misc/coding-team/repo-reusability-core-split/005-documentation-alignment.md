# Context

The current repository works, but its documentation still under-communicates the separation between reusable core, current project-specific content, and historical tooling.

# Objective

Update the main documentation so the repository is described as a reusable framework with explicit project-specific attachments and historical tooling boundaries.

# Scope

- Update:
  - `README.md`
  - `docs/README.md`
  - `docs/operational_pipeline_runbook.md`
- Align the documentation with the approved policy and entrypoint contract.
- Make explicit:
  - what this repository is
  - what is reusable core
  - what is project-specific
  - what the stable rebuild path is
  - what the runtime contract artifacts are
  - what scripts are historical

# Non-goals / Later

- Do not perform structural moves as part of this task.
- Do not document T27B physical changes yet.

# Constraints / Caveats

- No historical script may remain presented as the operational primary path.
- Keep language stable and durable; avoid task-history framing in the final docs.
- Documentation must remain consistent with the actual runtime and current scripts.

# Acceptance Notes

- A newcomer should be able to understand the reusable framework boundary from documentation alone.
