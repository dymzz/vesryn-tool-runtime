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


## Architecture decisions

For an important architecture decision, a revision or supersession of an existing
one, or an explicit request for an ADR, use the
[architecture-decision-record-skill](.agents/skills/architecture-decision-record-skill/SKILL.md)
in `.agents/skills/`. Ordinary bug fixes, dependency updates and local
implementations do not need an ADR.


## Delivery

- PR merging is authorized for this repository after task acceptance, code review and required CI checks on the current head.
- Before preparing a formal Release, review
  [Release Readiness](docs/delivery/release-readiness.md)
  and verify the applicable acceptance criteria.
  Readiness assessment does not authorize publication.
