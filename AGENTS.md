<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

# Project Working Conventions

These conventions apply to all code changes in this project, including small fixes and documentation that affects implementation behavior.

## Understand Before Editing

- Read the relevant existing code, configuration, tests, and project specifications before changing them.
- Preserve existing behavior and conventions unless the task explicitly requires a change.
- Identify affected modules, interfaces, data flow, and compatibility constraints before implementation.
- For unclear or multi-step work, state assumptions and acceptance criteria before writing code.

## Plan Before Code

- Break non-trivial work into small, independently verifiable steps.
- Separate requirements from technical design and execution details.
- Record important research, decisions, and discovered conventions in project files so they survive context compaction.
- Prefer the smallest change that fully satisfies the requirement; avoid unrelated refactors.

## Implementation Standards

- Follow the repository's existing architecture, naming, error handling, and dependency patterns.
- Keep ownership boundaries clear and avoid introducing abstractions without a concrete reduction in complexity or duplication.
- Validate inputs and failure paths at system boundaries.
- Add concise comments only for non-obvious reasoning; do not narrate self-evident code.
- Do not overwrite or revert unrelated user changes.

## Verification

- Run focused tests or checks for every change, then broaden verification when shared behavior or multiple layers are affected.
- Review the final diff for regressions, missing tests, accidental files, and consistency with the stated requirements.
- Do not claim a change is complete, fixed, or passing without current command output supporting that claim.
- When verification cannot be run, state the exact limitation and remaining risk.

## Knowledge Capture

- When a bug, technical decision, or reusable pattern is discovered, update the relevant `.trellis/spec/` documentation or project notes.
- Keep task requirements, implementation decisions, validation evidence, and follow-up work distinguishable.

## Completion Criteria

A change is complete only when the requested behavior is implemented, relevant checks pass, the affected files are reviewed, and any material project knowledge has been recorded. Use the Trellis task workflow for complex or multi-deliverable work; for simple changes, apply these conventions directly.
