"""TR-DISC-01C — issue #33 delivery record (rewritten scope)

Source: [issue #33](https://github.com/dymzz/vesryn-tool-runtime/issues/33),
rewritten 2026-10-25: "宿主 CLI 准备、SQLite 登记与共享工具名单". Prerequisites
#27 (PR #42) and #32 (PR #36) are merged; the old PR #37 scope (uv lock/
receipt backend migration) is superseded and this branch replaces it per the
issue ("[PR #37] 是旧范围的在审工作,应按当前已合入登记模型及本任务重新核对").
Git identity: `zcode <zcode@local>` (owner directive; the issue's suggested
`codex` attribution is not applied).

## What is delivered

**`host_tools.py`** — one preparation entry, two local stores, one shared
Agent list:

- `default_tools()`: the packaged read-only candidates
  (`vesryn_tool_runtime/data/default-tools.json`; vulture 2.16, hyperfine
  2.0.0). Reading, importing and SessionStart do nothing implicit.
- `prepare_tool(tool_id, *, ...)`: the single explicit entry. It probes the
  target shell first (reuse an entry that resolves and reports the selected
  version; report `conflict` with the existing version line instead of
  silently retargeting), installs what is missing through the real backends
  (`uv tool install <pkg>==<version>` for Python CLIs; the existing
  aria2 chain — source download, SHA-256 verify, safe extraction, ELF/PE
  header check — for native binaries, selecting the release whose
  platform/interpreter facts match this host), then registers in ONE
  operation updating both stores. Registration facts: `tool_install`
  (command, version, entry, description, prepared_via uv|aria2|external,
  reused, source_verified, registered_at) linked to the ToolAsset by
  `tool_id`; an external reuse without upstream evidence is recorded
  honestly with `source_verified=0` — never a fabricated download, and the
  executable's own file hash is never passed off as a verified publisher
  digest.
- **Two stores, one operation**: SQLite (facts) commits first, then
  `tools.json` is regenerated from the committed facts — stable-sorted,
  deduplicated, written via a same-directory temp file and `os.replace`
  (no cross-file atomicity claimed). A JSON write failure yields
  `registered_not_synced` with an explicit `refresh_tools()` rebuild;
  `uninstall_tool` removes the registration (uv environments via uv's own
  uninstall; native payloads stay in the existing asset store) and
  refreshes the list. Install failures never list the tool and never clear
  other entries.
- **Strict Agent list**: `tools.json` contains exactly `command` +
  `description`; the description is this task's independent one-liner (from
  the default list or explicit input), never the retrieval summary. Only
  commands the target shell resolves TO the registered artifact are listed —
  a registered native payload whose PATH is not yet prepared stays
  registered but unlisted, and a later `refresh_tools` lists it once the
  host exposes it; a same-name command from elsewhere is never listed.
  Python libraries/pytest plugins (no standalone CLI) and OCI-only records
  (no host install) are never listed as callable.
- **Root resolution**: `user_data_root()` — `VESRYN_TOOLS_HOME` overrides;
  otherwise `%LOCALAPPDATA%\vesryn\data` (Windows) or
  `$XDG_DATA_HOME|~/.local/share/vesryn/data`; creates nothing at import.
  No drive letters, usernames or source checkouts are hardcoded; every
  consumer (Vesryn #31's SessionStart) reads the same shared file.

**Selection without a capability contract** (`assets.py`): a selection's
`tool_contract_sha256` may be absent (dropped from documents, restored by
`from_document`), tool_id accepts bare identities — host preparation
freezes release facts straight from the record and never fabricates a
contract. The existing ECI lock/Dagger paths are untouched.

## Real evidence (2026-10-25, this host, no stubs)

| Step | Result |
| --- | --- |
| `uv tool install vulture==2.16` (real, outside the package) | `+ vulture==2.16`; `vulture --version` → `vulture 2.16`; entry `C:\Users\Aurola\.local\bin\vulture` |
| `prepare_tool("vulture")` against that shell | `reused` (`reused=true`, `source_verified=false` — honest: reuse without publisher-digest verification), entry recorded, `tools.json` written |
| `prepare_tool("hyperfine", aria2=<pinned 1.37.0>, allow_network)` | aria2 download + SHA-256 verify + safe extraction of the **windows msvc** release; `installed`, `source_verified=true`, entry = the asset-store payload path; `reused=true` on the second run (existing verified artifact reused, not re-downloaded) |
| Read-only runs of the actual entries | `hyperfine 2.0.0`; `vulture 2.16` — versions match the registered releases |
| `tools.json` after both | `[{"command": "vulture", …}]` — hyperfine registered but unlisted (its payload path is not on PATH; host-side PATH exposure is a startup concern), demonstrating the listing rule |

## Verification

| Evidence | Result |
| --- | --- |
| `tests/test_host_tools.py` | 10 passed — pure default read, root override/default rules, reuse without reinstall, version conflict reported not overwritten, uv install path (`tool install pkg==ver` asserted), native backend-required refusal, `registered_not_synced` + explicit rebuild, uninstall refresh, strict list shape with entry-not-ready exclusion |
| Full suite | 179 passed, 1 skipped (the pre-existing #8 concurrency case still flakes only on this Windows host) |
| Lint / format | clean |

Out of scope: no PATH/system modification by Runtime, no MCP/executor/
package-manager additions, ECI lock/Dagger paths unchanged, no release.
Handoff to Vesryn #31: `default_tools()` (candidates) vs `tools.json`
(callable list) distinction, `user_data_root()` resolution +
`VESRYN_TOOLS_HOME` override, `prepare_tool`/`refresh_tools`/
`uninstall_tool` signatures, and the SessionStart boundary (read the list,
never install).

## 2026-10-25 host-preparation extensions (final commit series)

The scope was rewritten by the owner on 2026-10-25: host CLI preparation,
SQLite registration and the shared Agent tool list (this record was
rewritten accordingly; the earlier uv-lock/receipt-migration content is
superseded).

- **Windows releases registered**: ripgrep 15.2.0, osv-scanner 2.6.0,
  actionlint 1.7.12, shellcheck 0.11.0, zizmor 1.31.1, trivy 0.76.1,
  deptry 0.25.1 — windows x86_64 digests verified against official
  GitHub Release / PyPI metadata and appended to the live declaration;
  stored asset rows sync to the declaration (header UPDATE + release
  replacement), so re-preparation after the declaration grows no longer
  fails with duplicate_tool_id.
- **Probe-first ordering**: prepare_tool probes the target shell before
  release matching — an entry that reports the SELECTED version is reused
  as-is (rg manually upgraded by the owner to 15.2.0 → reused,
  source_verified=false); an entry of another version is an honest
  conflict, never overwritten and never registered under the selected
  version.
- **~/.vesryn/bin exposure**: non-uv entries are exposed by copying the
  verified payload executable into ~/.vesryn/bin (VESRYN_BIN_HOME
  overrides); identical bytes are idempotent, different bytes are
  entry_conflict; uninstall removes the exposed copy while the verified
  payload stays in the asset store. All five newly prepared tools run
  read-only on this host: trivy 0.76.1, actionlint 1.7.12, shellcheck
  0.11.0, zizmor 1.31.1, osv-scanner 2.6.0.
- **tools.json** after the sweep lists nine commands (hypothesis,
  lint-imports, mutmut, py-spy, pyright, rg, schemathesis, tach,
  vulture); the five new entries appear once ~/.vesryn/bin is on PATH
  (host-side; the runtime never modifies PATH itself). memray stays
  excluded honestly — upstream publishes Linux/macOS only.

## 2026-10-26 review fixes (issue #33 acceptance re-audit)

The issue's acceptance list was re-audited against the code on this branch.
PR #37 carries no inline review comments on GitHub, so the findings below were
re-derived from the issue criteria and the delivered behaviour; each one is
now a directed test.

| # | Defect | Fix |
| --- | --- | --- |
| 1 | Reuse ignored the SELECTED version: `prepare_tool("vulture", version="2.16")` on a host reporting 2.14 returned `reused` and registered 2.14 | reuse requires the selected version; a mismatch is a `conflict` that reports what the entry actually shows |
| 2 | Version matching was a substring test — "2.0.0" matched "hyperfine 12.0.0" | versions are matched as whole tokens (`packaging.version` equality, so "2.16" == "2.16.0") |
| 3 | After `uv tool install` the probed version was discarded: a shadowing 2.14 entry was registered as 2.16 with `source_verified=true` | the resolved entry is re-probed and must report the selected version, else `conflict` with no registration |
| 4 | `uninstall_tool` never removed the exposure copy — the row was deleted before the entry was read back | the entry is read before the delete; an aria2 registration's own copy in the exposure directory is removed (the verified payload stays) |
| 5 | `uninstall_tool` ran `uv tool uninstall <command>` — wrong name for `import-linter` (command `lint-imports`) | the uv PACKAGE name is resolved from the declaration; the command is only the fallback |
| 6 | `_expose_native_entry` ignored the environ it was handed and wrote into the real `~/.vesryn/bin` | the exposure directory comes from the target environment (`VESRYN_BIN_HOME`) |
| 7 | `tools.json` listed any same-name command that resolved, not the registered artifact | a registration is listed only when the shell resolves exactly the recorded entry; a same-name binary elsewhere is not listed |
| 8 | The native path leaked raw `AssetError`/`StopIteration` instead of stable host reasons | `no_preparation_definition`, `no_preparation_release`, `invalid_backend`, `native_prepare_failed` |
| 9 | The default list shipped at `vesryn_tool_runtime/default-tools.json`; the issue contracts `vesryn_tool_runtime/data/default-tools.json` and the `data-include` glob pointed at a directory that did not exist | the resource moved to `data/default-tools.json`; the wheel ships `vesryn_tool_runtime/data/default-tools.json` |
| 10 | Dead and duplicated code: an unreachable second probe branch, an unused `_owned_by` helper, an unused parameter, and a `PREPARE_STATUSES` constant that did not match the statuses actually returned | removed; the constant now lists the returned statuses |
| 11 | A `.bat`/`.cmd` entry in a path with spaces was probed with an unquoted `cmd /c` line | the command line is quoted for `cmd.exe` |

Verification after the fixes: `tests/test_host_tools.py` 19 passed; full suite
188 passed, 1 skipped (the pre-existing #8 concurrency case still flakes only
on this Windows host); `ruff check` and `ruff format --check` clean; the built
wheel ships `vesryn_tool_runtime/data/default-tools.json` and
`default_tools()` resolves it from the installed layout.

The host registry was checked read-only: all 15 registrations still resolve to
their recorded artifacts, so the stricter list rule keeps the current nine
entries. A `refresh_tools()` run on the host adds the six native entries
(`actionlint`, `hyperfine`, `osv-scanner`, `shellcheck`, `trivy`, `zizmor`)
that are registered and now exposed through `~/.vesryn/bin`.
