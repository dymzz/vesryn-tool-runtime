# Python CLI shared definitions (TR-ASSET-CI-01B)

Group B delivery for [issue #17](https://github.com/dymzz/vesryn-tool-runtime/issues/17),
stage B of [issue #12](https://github.com/dymzz/vesryn-tool-runtime/issues/12), after the
shared read/assembly foundation of [issue #16](https://github.com/dymzz/vesryn-tool-runtime/issues/16).
Baseline: `main` at the #16 merge `3667238`, package version 0.2.0. The API is #16's;
this group adds data, a group test and this document only.

## Declared definitions

`src/vesryn_tool_runtime/shared_assets/python.json` is one bounded
`shared-asset-definitions` document (format in
[shared asset definitions](../shared-definitions.md)). It reuses the existing capability
identities and the frozen `catalog_revision` of the engineering-ci #51 records, and
declares one real publisher wheel per program:

| Asset ID | Existing capability | Version | Artifact | Platform | Requires-Python | Entrypoint |
| --- | --- | --- | --- | --- | --- | --- |
| `vulture` | `python.dead-code` | 2.16 | `vulture-2.16-py3-none-any.whl` | any/any | `>=3.9` | `vulture` |
| `pyright` | `python.typecheck` | 1.1.414 | `pyright-1.1.414-py3-none-any.whl` | any/any | `>=3.7` | `pyright` |
| `deptry` | `python.dependency-hygiene` | 0.25.1 | `deptry-0.25.1-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | linux/x86_64 | `>=3.10` | `deptry` |
| `pylint` | `python.duplicate-code` | 4.1.3 | `pylint-4.1.3-py3-none-any.whl` | any/any | `>=3.10.0` | `pylint` |

Every release is `distribution: python` / `backend: uv` and carries the publisher
URL and full lowercase SHA-256. Sources and hashes were re-read from PyPI for these
versions on 2026-10-24 and match the engineering-ci #51 frozen selections; the
definition digests of vulture, pyright and pylint reproduce that record
byte-for-byte. Asset IDs stay the canonical lowercase program names; the capability
IDs and their ToolSpec contracts are unchanged.

## Platform and ABI semantics (issue #29)

`abi` states the artifact's real C-library constraint, not a documentation note. The
three universal wheels are genuinely platform-independent and keep `abi: null`; deptry
declares `abi: gnu` because its wheel is `manylinux_2_17_x86_64` (glibc). Per the
[PyPA platform tag specification](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/)
manylinux means glibc and musllinux means musl, and `linux`/`x86_64` alone does not
equate the two. Consequences, enforced by selection **and** by uv admission:

- An explicit `AssetTarget("linux", "x86_64", abi="musl")` can no longer select the
  deptry wheel (`unsupported_target`), and the uv backend resolves it with the
  `x86_64-unknown-linux-musl` triple — never a silent GNU one.
- A Linux target with no ABI states an unknown C library. It is explicitly rejected
  (`unsupported_target`) rather than treated as unconstrained: a glibc-constrained
  artifact is not reported usable where compatibility cannot be proven. Consumers
  whose real environment is glibc (the ECI Dagger containers) state `abi: "gnu"`.
- The uv backend reads the wheel's own filename (`manylinux…`/`musllinux…`) and
  admits only a matching Linux/libc target, so an old mislabeled selection cannot
  pass execution admission on the wrong libc even though the frozen file itself
  stays readable as history.

## The deptry platform correction

The #51 record declared the manylinux x86_64 wheel with `os: any` and `arch: any`,
which let a Windows or macOS target select a wheel it cannot install. Correction
came in two steps: #17 stated `os: linux`, `arch: x86_64`; #29 added
`abi: gnu`. The artifact URL and SHA-256 are unchanged.

The correction changes only declaration identity:

| Fact | Before (#51 record) | After |
| --- | --- | --- |
| `definition_sha256` | `6ee56d9c…66320` | `94f89828…cc97` |
| `artifact_id` | `3886c0dd…7434` | `b08b8990…05f0` |
| `selection_id` (same target/policy) | `5e8f46e6…d3fa` | `d44944d6…a722` |
| lock `requirements_sha256` | `be985aac…7632` | `be985aac…7632` (unchanged) |

The Linux x86_64 / Python 3.14 lock re-resolved with uv 0.12.23 produces the identical
requirement text, so the platform fix does not change the installed wheel set; only the
derived selection and artifact identities must be regenerated.

Frozen history stays readable. `AssetSelection.from_document` still accepts the #51
deptry selection unchanged (`release.os`/`arch` remain `any`, its own
`definition_sha256` and `selection_id` stay self-consistent), and the old document is
never rewritten. A current selection against a Windows target now fails with the
existing `unsupported_target` instead of choosing the Linux wheel.

Consumers in engineering-ci (#52/#53) must regenerate `deptry.selection.json` and its
lock from the corrected definition. This repository does not edit the consumer
worktree or replace its lock files.

## Reading and assembling

No ECI checkout, adapter, installer or network is involved.
The example selects a Linux x86_64 target already known to use glibc:

```python
from vesryn_tool_runtime import (
    AssetPolicy,
    AssetTarget,
    load_shared_definitions,
    register_shared_definitions,
)

records = load_shared_definitions("python.json")  # bundled name, pure read
register_shared_definitions(tools, records)  # capabilities must exist already
selection = tools.select_asset(
    "python.dependency-hygiene",
    target=AssetTarget("linux", "x86_64", abi="gnu", python="3.14"),
    policy=AssetPolicy("eci-tools-2026-10-23"),
)
```

The [0.3.1 release evidence](https://github.com/dymzz/vesryn-tool-runtime/releases/tag/v0.3.1)
retains the failing and corrected consumer runs. The local uv preparation example
detects its host libc; its GNU-container lock is a separate explicit target.

The bundled document is returned by `shared_definition_documents()` and ships inside
the wheel with no manifest or `pyproject` change. Association still requires each
capability to be registered with its real ToolSpec and adapter; the definition never
creates a capability and grants no install or execution right.

## What is not delivered

- No ToolSpec or Adapter for the four engineering-ci check capabilities exists in this
  repository. The group test uses an association-only adapter to prove the Catalog
  relationship; it does not make `python.dead-code`, `python.typecheck`,
  `python.dependency-hygiene` or `python.duplicate-code` callable here.
- Nothing is installed or executed by this task on Linux. The first proof target is
  Linux x86_64 / Python 3.14; a registration is not an installation and not a scan
  result. The #7 delivery already prepared the identical vulture 2.16 wheel on
  Windows, and #51 produced the four Linux locks; those records are cited, not rerun.
- Pyright's execution still needs Node. `nodeenv` is a package dependency and the Node
  requirement remains a consumption condition; no Node installer is added and the
  engineering-ci container assembly is not copied here.
- Other deptry wheels (Windows, macOS, aarch64, musllinux) exist upstream but are not
  declared, because only the Linux x86_64 target is covered by the current evidence.
  Windows/macOS/ARM verification is therefore `not_verified` for deptry.

## Verification

- Group test: `tests/test_shared_assets_python.py` (offline; identities, assembly,
  the platform correction and the frozen old selection).
- Common compatibility test: `tests/test_shared_definitions.py` from #16 — cited, not
  copied or rerun by this group.
- Recorded evidence: [verification/tr-asset-ci-01b.json](../verification/tr-asset-ci-01b.json)
  and the [issue #17 delivery record](../tasks/vesryn-tool-runtime/P1-python-cli-shared-assets.md).

Up: [Shared asset definitions](../shared-definitions.md) · [Documentation](../README.md).
