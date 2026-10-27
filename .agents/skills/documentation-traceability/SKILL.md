---
name: documentation-traceability
description: >
  Use when planning or updating architecture documentation, defining or linking
  ADR and Spec Needs in Sphinx-Needs, mapping source CodeLinks or JUnit test
  evidence, updating Python API references, or analyzing documentation impact
  from code changes. Do not use for routine prose or formatting edits.
---

# Documentation Traceability

## Core Philosophy

1. **Authority by Information Type**:
   - Specs define intended behavioral contracts and traceable requirements.
   - ADRs preserve architectural decisions, rationale, alternatives,
     consequences, and typed relationships.
   - Source code and schemas describe actual implementation and structure.
   - Guides prioritize runnable usage and operator workflows.
   - Preserve machine-readable IDs, relationships, and complete ADR content.
     Do not mistake implementation state for normative requirements.

2. **Code and Structure as Documentation**:
   - Generate mechanically derivable API signatures and schema structures.
   - Document intent, behavioral semantics, cross-module constraints,
     rejected alternatives, compatibility and operational limitations.
   - Avoid maintaining duplicate representations of the same facts.

## Workflow & Conventions

1. **Read Selective Context**:
   - Read the repository's current documentation entry (`docs/README.md`) and
     only the contracts relevant to the task.
   - For planning, use explicitly supplied upstream plan chapters as design
     input; do not assume unprovided external plans are accessible or already
     implemented.

2. **Specifications and Decisions**:
   - Keep current behavioral contracts in their owning documentation.
   - Create a stable `SPEC_` Need only where independent references or
     traceability are required; do not wrap every paragraph.
   - Keep historical decision rationale in ADRs rather than duplicating
     it inside current Specs.

3. **ADRs and Full-Content Export**:
   - Use `architecture-decision-record-skill` to decide whether an ADR
     is warranted and to structure its content.
   - New standalone ADRs use
     `docs/adr/<imperative-verb-phrase>.md`.
   - Use one MyST colon-fenced `adr` Need per standalone ADR, with
     Context, Decision and Consequences inside the directive.
   - Keep `:status:` as the single authoritative status value:
     proposed, accepted, rejected, superseded or deprecated.
   - Use only link types declared in the repository's Sphinx-Needs
     configuration. `decides` targets Specs; `supersedes` targets ADRs
     when those link types are configured.
   - Minor clarifications edit the existing ADR. A decision that
     replaces another gets a new ADR and an explicit supersession link.
   - Preserve existing Need IDs when reorganizing older documents.
   - Verify the full body is present in `needs.json.content` and that
     the HTML output is readable.

4. **Reuse Existing Traceability & API Tools**:
   - **Source tracing**: reuse CodeLinks (`@need-ids:` referencing existing
     Needs). CodeLinks represents declared source associations and does not
     prove an implementation satisfies its contract; Git Diff scope mapping
     belongs to downstream impact analysis.
   - **Test evidence**: reuse original JUnit evidence and `ub-test-reports`
     (keep converted test Needs separate from the main documentation
     `needs.json`). Never re-run tests solely for conversion.
   - **Python API**: reuse Sphinx AutoAPI for API reference generation and
     Griffe for breaking-change detection.

5. **Verify & Respect Delivery Boundaries**:
   - Reuse the existing Sphinx HTML build and its `needs.json`; rerun
     (`sphinx-build -b html -n -W --keep-going`) only when changed inputs
     invalidate the available result.
   - Reuse valid verification evidence and report unresolved relationships or
     unmapped code as explicit coverage gaps rather than inventing them.
   - Keep repository implementation plans and delivery history in their owning
     Issue/PR workflow. Do not create standalone completion reports.
