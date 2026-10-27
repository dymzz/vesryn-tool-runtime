# Persist Installation Provenance

:::{adr} Persist installation provenance
:id: ADR_TR_PERSIST_INSTALLATION_PROOF
:status: accepted
:decides: SPEC_TR_MAIN_ARTIFACT_PROOF

## Context

`prepare_tool()` registers local CLI tools in `tools.sqlite3` (`tool_install`) and exposes callable commands in `tools.json`. Over time, bundled release declarations in `record_seed.sql` can update digests or release URLs, download caches under `tool-assets/` can be cleaned or populated independently of what was installed, and pre-existing CLIs on `PATH` can be reused (`prepared_via = 'external'`).

Three approaches were considered for tracking whether an installed tool matches a verified release artifact:

- **Persist a `source_verified` boolean in `tool_install` (Schema v3)**: Rejected. A stored boolean is not bound to specific artifact bytes. If `record_seed.sql` updates the release URL or SHA-256 for a version, a previously stored `1` remains truthy for bytes never verified against the new declaration; conversely, re-preparation risked conflating installation ownership (`prepared_via`) with provenance verification.
- **Infer provenance from the download cache path**: Rejected. An archive or wheel present in `tool-assets/` does not prove it was the artifact used to install the active entry, and pruning the download cache would falsely erase provenance for an unchanged environment.
- **Persist the verified installation source URL and SHA-256 independently on `tool_install` (Schema v4)**: Selected.

## Decision

Record the verified main-artifact provenance (`verified_source` and `verified_sha256`, either both non-empty or both `NULL`) directly on `tool_install` in SQLite Schema v4, independent of installation ownership (`prepared_via`), and compute `source_verified` dynamically against the active `ToolAssetVersion` release declaration (`version`, `source`, `digest`) for the target platform.

When inspecting or reusing an unchanged environment, preserve existing provenance; when explicit uv plugin reconciliation (`with_packages`) must establish new main-artifact provenance, pass `--reinstall-package` for the main wheel without forcing all dependency packages to reinstall. Keep `tools.json` strictly limited to Agent-facing `name`, `command`, and `description` entries.

## Consequences

- **Positive**: Installation provenance is bound to the exact artifact URL and SHA-256 used at installation time rather than mutable seed declarations or ephemeral cache files. Installation ownership (`prepared_via`) remains decoupled from provenance so `uninstall_tool()` only removes runtime-owned assets while external or unverified CLIs remain usable.
- **Cost**: Requires an explicit [SQLite Schema v3 to v4 boundary](../discovery-contracts.md#migration-boundary-explicit) (`record_schema = 4`). `open_record_store()` rejects v3 stores until `upgrade_record_store()` runs; upgrading clears historical boolean verification to `NULL` (`verified_source = NULL, verified_sha256 = NULL`) because a boolean cannot reconstruct artifact identity.
- **Limitations**: Captures installation-time provenance of the primary tool artifact only; it does not re-verify executable files modified outside the runtime after installation, nor does it claim publisher digest provenance for every transitive dependency or plugin package.

:::
