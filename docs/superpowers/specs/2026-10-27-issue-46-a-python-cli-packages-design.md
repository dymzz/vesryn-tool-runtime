# Issue #46 A: Python CLI plugin requirements

This is the A-stage design for [issue #46](https://github.com/dymzz/vesryn-tool-runtime/issues/46), refined from the short design reviewed in this chat. Baseline: `98c8c27c4528fa0e65095d5a5192ed959e0d7d8e` (P0 #45 and installation provenance #47). B/C remain separate acceptance stages. This document is a design, not an execution report.

## Approach and boundaries

Extend the existing `prepare_tool` / `_uv_install` chain with uv-native `--with` requirements. The alternative `--with-requirements` is supported upstream, but a file input adds no value for two pinned plugins. No other installer, record registry, environment manager or receipt database is added. Plugin packages are not independent Agent tools.

`prepare_tool(..., with_packages=None)` has these semantics:

- `None`: preserve the existing preparation/reuse behavior.
- A list/tuple, including `()`: explicitly select the complete additional-requirement set. Empty means reconcile to no explicitly requested plugins, not "ignore the old set". A package still needed transitively may remain installed.
- Entries are `name==version` only. Use `packaging.Requirement` and `Version`; reject URLs, paths, markers, extras, wildcards, ranges and contradictory duplicate names. Normalize names, deduplicate identical pins, sort deterministically and reject an additional pin for the main package. Reject explicit package requests on non-uv tools before side effects.

The `None`/empty distinction is an implementation refinement to preserve old callers and make removal expressible without a schema migration.

## Declarations

Add one bundled `ToolAsset`: `tool_id=sphinx`, `provider=uv`, `package=sphinx`, `entrypoint=sphinx-build`. Its `ToolAssetVersion` declares the universal main wheel and Python `>=3.13`. Keep the existing record types and frozen schema unchanged. Synchronize the repository's derived example library through the existing record-store path.

Candidate direct pins and official wheel metadata (not yet installation evidence):

| Package | Version | Wheel SHA-256 |
| --- | --- | --- |
| Sphinx | 9.2.0 | `4c3ec13b612712c0d3ce4cbdd9e3eb91e68577e07a8e31f32f21cf178453578c` |
| myst-parser | 5.1.0 | `9c91c52b3cdb4d94a6506e4fab4e2f296c7623a0da0dcbe6de1565c3dad67a8a` |
| sphinx-needs | 9.1.0 | `888fbe9e0b2b6121ef32e254364dbf8d869c7120e9dc4128311cec494c54e106` |

The Sphinx declaration source is `https://files.pythonhosted.org/packages/c4/28/a0c50761cd215b7042f4bc617a6bc5c0cd7be62f75bc908e169e28a4d21e/sphinx-9.2.0-py3-none-any.whl`.

Official plugin wheels: [MyST](https://files.pythonhosted.org/packages/09/dc/f3dfb7488b770f3f67e6545085bf2abea5172e88f57b8ad25ef860ca704c/myst_parser-5.1.0-py3-none-any.whl), [Needs](https://files.pythonhosted.org/packages/d0/3a/8f676729f3c90f1ee8d5d04a01e586386ffe28941c32ac53c7231bc450a1/sphinx_needs-9.1.0-py3-none-any.whl). These record publisher metadata; uv still resolves pinned plugin requirements and their transitive dependencies. Do not assert the installed plugin wheel bytes equal these references unless independently observed and checked.

Python metadata intersects on Python 3.14; MyST and Needs accept Sphinx 9.2.0 and have overlapping Docutils requirements. Actual compatibility requires the A-stage same-environment import probe.

## Existing-entry and uv behavior

Keep the existing CLI version conflict behavior. For an explicit package request, a version probe alone never establishes reuse:

1. Read the actual uv-managed tool entry, environment path and additional requested pins using `uv --no-config --color never tool list --show-paths --show-with` (without network/outdated checks). Cross-check the target shell's executable against that registered entry.
2. Use that tool environment's Python with `-I -B` to read its prefix, Python version and installed distribution versions; use `uv pip check --python <that interpreter>` to establish dependency consistency. Never substitute the project environment or a bare `python`.
3. Reuse only when the actual entry/main version, complete recorded requested set, installed required versions and dependency checks all agree. Preserve the existing main-artifact source proof; inspection cannot create it.
4. If the known uv tool needs a different set or repair, pass the complete canonical set and the existing verified main wheel to `uv tool install --python ... --with ...`. Do not default to `--force` or reinstall all packages. An external/unidentifiable same-name entry is `conflict`, not permission to overwrite it.
5. A prior uv environment lacking a matching recorded main-artifact proof must not gain `source_verified=True` from a successful uv no-op or dependency-only change. If this explicit preparation establishes new main provenance, require uv's package-specific main reinstall from the verified wheel. Otherwise retain the unknown proof honestly.
6. After uv returns, inspect the actual managed environment and target-shell entry again. Missing/malformed evidence, wrong versions, dependency errors or a shadowing executable cannot produce a successful registration.

Normal same-environment reuse returns `reused`; newly prepared/reconciled requested configurations return `installed`. `installed` does not assert every dependency was downloaded or replaced. The uv operation's free-text diagnostics are not parsed to infer reuse. Existing `conflict`, failed-install and `registered_not_synced` meanings remain authoritative.

Forward the effective `environ` to uv processes. Real verification sets `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR`, `UV_CACHE_DIR` and Runtime roots inside this worktree's existing `.tmp/issue-46-a/`; no global tool or shell configuration is changed.

## Evidence and bounded compatibility

Add an `environment` result only for explicit-package preparation, with keys `python`, `prefix`, `python_version`, `with_packages`, `packages` (sorted `{name, version}` records), and `dependencies_consistent`. These are actual observed tool-environment facts, not predictions from the requested pins. Preserve `source_verified` as main-artifact evidence only; no field claims an entire environment hash. Do not change SQLite tables, public ToolAsset/ToolAccess identities, or the strict command/description shape of `tools.json`.

uv 0.12.23 is verified for its public text view. It has no structured tool-list output; keep parsing narrow, bounded and fail closed on unsupported output rather than depending on private `uv-receipt.toml` or cache layouts. This is an observed upstream automation limitation, not a confirmed uv bug.

A verifies the new interface, current host-tool regressions, one actual Runtime preparation and `sphinx-build --version`, then imports `sphinx`, `myst_parser` and `sphinx_needs` with that exact tool Python. B reuses the resulting evidence and performs its own lifecycle acceptance; C alone adds Sphinx/Needs configuration and builds HTML/JSON. No ECI/Dagger/Actions documentation integration, Release or issue closure is part of A.

Primary references: [uv plugin dependencies](https://docs.astral.sh/uv/concepts/tools/#including-additional-dependencies), [uv 0.12.23 install implementation](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv/src/commands/tool/install.rs), [uv list implementation](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv/src/commands/tool/list.rs), [Sphinx](https://pypi.org/project/Sphinx/9.2.0/), [MyST](https://pypi.org/project/myst-parser/5.1.0/), [Needs](https://pypi.org/project/sphinx-needs/9.1.0/).
