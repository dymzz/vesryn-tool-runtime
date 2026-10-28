# Vesryn Tool Runtime — Agent Instructions

所有访问其他目录的行为都需要手动批准

Start at [docs/README.md](docs/README.md). Public technical documentation belongs
under `docs/`. Keep version-specific evidence linked from the delivery assessment.

This package owns generic tool contracts, Catalog, explicit Provider composition,
discovery, selection binding, admission, batch dispatch and result validation.
Never import Vesryn, engineering-ci, workflow scheduling/checkpoints or logging
storage. Execution implementations stay behind ToolAdapter. Preserve adapter
batches and original outcomes. Only explicit host scope admits execution.

Use vesryn-log's public EventSink protocol, allowlist safe event fields, and report
recording failures independently. Never log parameters or raw adapter diagnostics.

## Code Comments & Docstrings

- **Public APIs**: Document exported behavioral contracts with concise docstrings. Explain relevant preconditions, side effects, errors, and resource ownership; avoid duplicating type signatures or existing specifications.
- **Inline Comments (`#`)**: Write only when intent, reasoning, or constraints are not evident from names, types, or code structure. Prioritize *why*, *trade-offs*, and *invariants* over narrating *what*.
- **Valid Cases**: Complex algorithms/formulas (including meaning, units, or references), non-obvious state transitions, concurrency/transaction ordering, resource lifecycles, subtle edge cases, security boundaries, compatibility workarounds (with removal conditions when known), and unusual optimizations.
- **Prohibitions**: Do not narrate obvious code, echo task prompts or change history, retain commented-out dead code, or add broad lint/type suppressions without a specific rule and nearby justification.
- **Traceability**: Preserve valid structured markers such as `@need-ids:`. When refactoring, update their locations or references to match the actual implementation; never silently remove or leave stale links.

## Architecture Documentation

Code, types, schemas, and structured relationships are primary documentation; prose records only contracts, boundaries, and decisions that code and structure cannot express.

For architecture planning and traceability tasks, use the
[documentation-traceability](.agents/skills/documentation-traceability/SKILL.md) skill and relevant current docs.

Use [architecture-decision-record-skill](.agents/skills/architecture-decision-record-skill/SKILL.md) when a significant decision, or a revision/supersession of an existing one, merits an ADR. Do not create ADRs for routine changes.

External plan chapters are design inputs only when supplied
for the task; they are not automatically current repo contracts.


## Delivery

- PR merging is authorized for this repository after task acceptance, code review and required CI checks on the current head.
- Before preparing a formal Release, review
  [Release Readiness](docs/delivery/release-readiness.md)
  and verify the applicable acceptance criteria.
  Readiness assessment does not authorize publication.
