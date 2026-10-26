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
  (for Python CLIs: the SELECTED artifact is fetched (or taken from the
  asset root), its SHA-256 is checked against the publisher's digest, and
  THAT verified file is what uv installs — `uv --no-config [--offline] tool
  install <verified artifact>`; the existing aria2 chain — source download,
  SHA-256 verify, safe extraction, ELF/PE header check — for native
  binaries, selecting the release whose platform/interpreter facts match
  this host), then registers in ONE
  operation updating both stores. Registration facts: `tool_install`
  (command, version, entry, description, prepared_via uv|aria2|external,
  reused, source_verified, registered_at) linked to the ToolAsset by
  `tool_id`; an external reuse without upstream evidence is recorded
  honestly with `source_verified=0` — never a fabricated download, and the
  executable's own file hash is never passed off as a verified publisher
  digest. The verification state belongs to ONE artifact: the recorded
  (tool, version, entry) AND the declared release's publisher digest. A
  re-preparation keeps the owner of that entry (a fact about the entry) and
  keeps the verification only while the declared artifact is still the one
  the asset store holds — that store is keyed by the publisher digest, so
  the path IS the artifact's identity.
- **Two stores, one operation**: SQLite (facts) commits first, then
  `tools.json` is regenerated from the committed facts — stable-sorted,
  deduplicated, written via a same-directory temp file and `os.replace`
  (no cross-file atomicity claimed). A JSON write failure yields
  `registered_not_synced` with an explicit `refresh_tools()` rebuild;
  `uninstall_tool` removes the registration (uv environments via uv's own
  uninstall; native payloads stay in the existing asset store) and
  refreshes the list in the same target environment the preparation used.
  Install failures never list the tool and never clear other entries.
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
| manual `uv tool install vulture==2.16` (real, outside the package; the runtime itself installs the verified artifact — finding 20) | `+ vulture==2.16`; `vulture --version` → `vulture 2.16`; entry `C:\Users\Aurola\.local\bin\vulture` |
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
`uninstall_tool` signatures (all three take the target `environ`; the
uninstall rebuilds the list in it), and the SessionStart boundary (read the
list, never install).

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
| 12 | The runtime could not replace its OWN previous copy, so a tool could never be upgraded — every re-preparation ended in `entry_conflict` | our own recorded copy is replaced (an upgrade); a file of unknown ownership is still refused |
| 13 | The legacy release lookup ignored the ABI, so a same-version release of another ABI could be picked | the ABI is part of the lookup |
| 14 | `reused` carried two meanings: "an existing command of unknown ownership was taken as-is" and "the verified payload was already in the asset store" | the native path reports `reused` when the payload was reused; both meanings are documented |
| 15 | `user_data_root()` ignored the caller's environment, so `VESRYN_TOOLS_HOME` came from the host process | the root follows the target environment |
| 16 | An empty target PATH fell back to the host's PATH | an empty PATH resolves nothing |
| 17 | `tools.json` was written through a fixed temp name, so concurrent writers collided | a unique temp name in the same directory |
| 18 | The declaration had no windows x86_64 ripgrep release although this record claimed one — `prepare_tool("ripgrep")` raised `missing_release` on this host | the official `ripgrep-15.2.0-x86_64-pc-windows-msvc.zip` release was added with the publisher digest (`71b2fef8…`) taken from the GitHub release metadata; the committed demo library was regenerated from schema+seed |
| 19 | The `AssetSelection` construction validates that the legacy release matches the target; its `invalid_selection` was raised outside the guarded block and still leaked a raw `AssetError` | the selection is built inside the guard, so every native failure is a stable host reason |
| 20 | The Python install handed the backend only `uv tool install <pkg>==<ver>` — no offline flag, no selected source, no digest constraint — and still recorded `source_verified=true`; a version probe cannot prove the installed artifact matches the registered SHA-256 | the SELECTED artifact is fetched (or taken from the asset root), its SHA-256 is checked against the registered digest, and THAT file is what uv installs (`uv --no-config [--offline] tool install <verified artifact>`); an unverifiable artifact is never installed |
| 21 | The offline requirement never reached the backend: `allow_network=False` was not passed to uv at all | the offline requirement reaches uv itself as `--offline`; without network permission only an already-verified artifact in the asset root is used, a missing one is `offline_missing` |
| 22 | A version probe that FAILED (non-zero exit) was still read as a usable entry — the output's version was enough | the probe's exit code is part of the fact: a failed probe is a `conflict` that reports the failure, and nothing is registered for it |
| 23 | Preparing a tool twice dropped the installation ownership (`prepared_via` became `external`), so the uninstall no longer cleaned up the environment the runtime had installed | a re-preparation keeps the recorded owner and verification state of that same entry; an entry the runtime never registered stays an honest external reuse |
| 24 | A failing uninstall still reported `uninstalled` and the registration was already deleted | the backend's result decides: a failed uninstall keeps the registration and the list entry and reports `uninstall_failed`; the registration is dropped only after the removal actually happened |
| 25 | A delayed publisher could write a stale list over a newer one (the unique temp file only fixed the file-name collision) | the registration and the list snapshot are published under the store's existing `FileLock` coordination, and the snapshot is always rebuilt from the committed facts inside that lock |
| 26 | `platform=linux` was parsed as `posix` and never matched the records' `linux` | the host OS is resolved through the existing platform maps (`uv_assets.host_platform`), so `linux`/`win32`/`darwin` and the record vocabulary all resolve to `linux`/`windows`/`macos` |
| 27 | The Python artifact's location was decided inside `host_tools.py`, so the asset root had two layout conventions, and this record claimed a host path (`tool-assets\python\...`) that does not exist on this host | the layout lives with the other asset-root layouts (`asset_index.python_asset_directory`, next to `native_asset_directory`): asset, version and publisher digest, with the wheel's own file name inside it, because uv installs a local artifact by that name; this record states the real path |
| 28 | The digest check had no directed test, and the one test that reached it read the HOST's real asset root — it would have failed as soon as the host cached an artifact, and the corrupt/mismatching paths were untested | the check is hermetic (the asset root is pointed at a temp dir), and the corrupt cached copy and the mismatching download are directed tests: neither is ever installed |
| 29 | `uninstall_tool` rebuilt the list in the HOST's shell: a tool that only resolves in the target shell was dropped from the shared list, so uninstalling one tool silently emptied the list | the uninstall takes the target environment and rebuilds the list in it; a directed test uninstalls one of two target-only tools and keeps the other listed |
| 30 | The lock-coordinated publication left the old `_write_tools_json` behind: dead code, and a trap — it called `refresh_tools`, which takes the same lock, so calling it from inside the locked publication would have waited for itself | removed |
| 31 | The artifact download wrote through a fixed `<name>.part` file: two concurrent downloads of the same artifact wrote into one file, the bytes interleaved and both verifications failed | a unique temp name in the same directory (the pattern the shared list already uses), and the partial file is removed on every failure path |
| 32 | The declaration's deptry Windows release carried `abi: gnu` — copied from the manylinux row — so the host (windows → msvc) could not select it at all; it was the only Windows row in the whole declaration with a glibc ABI | the row states `abi: msvc`, like the other Windows wheels (py-spy, tach); the publisher digest was re-verified against the publisher's own bytes before the correction, and the committed demo library was rebuilt from schema+seed |
| 33 | The tool environment's interpreter was left to the backend: uv picks one on its own, and on a free-threaded host that pick cannot load the stable-ABI (abi3) wheels publishers ship — the install failed with "the wheel was built for the stable ABI, which requires a GIL-enabled interpreter" | the interpreter is NAMED: the running one when it can load the artifact, otherwise a GIL-enabled interpreter of the same version from the target PATH; a host with neither reports `interpreter_unavailable` instead of a backend dump |
| 34 | The recorded owner and verification state were inherited by (tool, entry) alone: after a version switch, the new version's registration inherited the OLD version's `source_verified=true` and its installation owner — a version the runtime never downloaded nor verified | the facts belong to ONE artifact: the recorded (tool, version, entry). A different version at the same path is another artifact, so it is recorded as an honest external reuse (`prepared_via=external`, `source_verified=0`) |
| 35 | Matching the VERSION was still not matching the ARTIFACT: a declaration that now offers another artifact for that version (a corrected digest, another platform/ABI release under the same version) kept the earlier registration's `source_verified=true` — a claim about bytes the runtime never verified | the verification state is checked against the artifact's identity: the DECLARED release's publisher digest must be the one the asset store holds (the store is keyed by that digest, so the path IS the identity). The owner is a fact about the ENTRY and is kept; the verification fact about a different artifact does not carry |

Verification after the fixes: `tests/test_host_tools.py` 40 passed; full suite
209 passed, 1 skipped (the pre-existing #8 concurrency case still flakes only
on this Windows host); `ruff check` and `ruff format --check` clean; the built
wheel ships `vesryn_tool_runtime/data/default-tools.json` and
`default_tools()` resolves it from the installed layout.

### The two local stores stay what they are

The user data root is `%LOCALAPPDATA%\vesryn\data` (`$XDG_DATA_HOME|~/.local/share/vesryn/data` elsewhere), and it holds exactly two things:

- `tools.sqlite3` — the registration facts: which tool, which version, which
  entry, who owns the installation, whether the source was verified;
- `tools.json` — the Agent-facing list: strictly `command` + a short
  `description`, sorted and deduplicated. This is the file a consumer hook
  mounts at SessionStart; it is NOT the registry and must not be treated as
  one.

Verified artifacts (the fetched Python wheels) live in the asset root
(`%LOCALAPPDATA%\vesryn\tool-assets` on Windows), never in the user data root,
so the list is never confused with the installation facts. A wheel sits at
`<asset root>\python\asset-<tool_id>\version-<version>\<publisher digest>\<wheel
file name>` — the digest is the directory, the wheel keeps its own name, and
only those bytes are ever handed to the installer.

The host registry was checked read-only: all 15 registrations still resolve to
their recorded artifacts, so the stricter list rule keeps the current nine
entries. A `refresh_tools()` run on the host adds the six native entries
(`actionlint`, `hyperfine`, `osv-scanner`, `shellcheck`, `trivy`, `zizmor`)
that are registered and now exposed through `~/.vesryn/bin`.

### 2026-10-26 the host list, brought up to date

The host's `tools.json` was rebuilt from the host's own registrations with an
explicit `refresh_tools()`: the list went from nine entries to the 15 that
resolve, and then to 16 after `deptry` was prepared. Read-only checks on the
host: all 16 registrations resolve to their recorded artifacts, the six native
entries resolve to their exposure copies in `~/.vesryn/bin`, and `rg` resolves
to the owner's own `D:\Tools\rg` — an honest external reuse, recorded as
`prepared_via=external`, `source_verified=0`.

`deptry 0.25.1` was prepared through the runtime on this host: the selected
Windows wheel was fetched, its SHA-256 checked against the publisher's digest,
and that verified file installed — `installed`, `source_verified=true`, entry
`~\.local\bin\deptry.EXE`, and `deptry --version` → `deptry 0.25.1`. The
install needed the interpreter to be NAMED (finding 33): this host's project
interpreter is a free-threaded CPython 3.14 (`cp314t`), which cannot load the
wheel's stable ABI.

`pylint` was NOT prepared, and the runtime said why instead of forcing it: the
host already resolves `pylint` to `D:\SDE\Python\Python314\Scripts\pylint.EXE`,
which reports 4.1.2, while the declaration offers 4.1.3. That is an honest
`conflict` — the existing entry is never overwritten and never registered
under another version.
