# TR-ASSET-PLATFORM-01 — issue #29 delivery record

Source: [issue #29](https://github.com/dymzz/vesryn-tool-runtime/issues/29), from the
[#12](https://github.com/dymzz/vesryn-tool-runtime/issues/12) delivery review of the
original #17 / PR #23. The issue's local task-book path does not exist in this
checkout; this record is created from the fetched issue #29 body.

Baseline: main `098bf4d` (v0.3.0 plus the #30 Semgrep evidence docs). No release is
performed; the package version stays 0.3.0. Git identity for this branch is
`zcode <zcode@local>` per the repository owner's instruction.

## What changed

- **`shared_assets/python.json`** — deptry 0.25.1's release now declares
  `abi: "gnu"` (its wheel is `cp310-abi3-manylinux_2_17_x86_64`, i.e. glibc).
  The artifact URL and SHA-256 are unchanged; the new definition digest is
  `7cf1b54637d47b66d029d018d808843e6ea97af94a2864bea54e81ae6c1db5d6`
  (previous corrected digest `94f89828…4cc97`, original #51 digest
  `6ee56d9c…a66320`). The three universal wheels keep `abi: null` because they
  are genuinely platform-independent.
- **`uv_assets.py`** — the resolved triple now follows the target's real C
  library instead of assuming GNU for every Linux target:
  - Linux requires an explicit `abi`: `gnu` → `*-unknown-linux-gnu`,
    `musl` → `*-unknown-linux-musl` (x86_64 and aarch64). An ABI-less Linux
    target states an unknown libc and is rejected with
    `AssetError("unsupported_target")` — it is never silently resolved as GNU.
  - Admission reads the wheel's own filename (`manylinux` = glibc,
    `musllinux` = musl, per the PyPA platform tag specification): such a wheel
    only reaches a Linux target whose `abi` matches, so an old mislabeled
    declaration or frozen selection cannot execute on the wrong libc or on
    Windows, while a genuinely glibc target still passes.
- **`assets.py` matching is unchanged** — `matches()` already treats a declared
  ABI as an exact constraint and `abi: null` as genuinely unconstrained; the
  defect was the mislabeled data plus the uv mapping, both fixed above.

## Directed acceptance

| Requirement | Result |
| --- | --- |
| Known-compatible existing Linux/glibc targets still select the right artifact with consistent uv args | `tests/test_shared_assets_python.py` and `tests/test_uv_assets.py`: gnu targets select deptry and resolve `x86_64-unknown-linux-gnu`, exactly as before. |
| An explicit musl request can neither select the manylinux artifact nor be silently switched to GNU | Selection: `unsupported_target` (`test_deptry_platform_correction_blocks_incompatible_targets`). uv: musl targets resolve `x86_64-unknown-linux-musl`, and the manylinux-named wheel never reaches a musl/unknown-ABI/Windows target (`test_platform_wheel_libc_is_read_from_the_artifact_name`). |
| Unknown targets without provable compatibility get an explicit result | An ABI-less Linux target is `unsupported_target` at selection (deptry) and at uv admission (any Linux target); unknown never means "no platform restriction". |
| No preservation of old `abi: null` or old digests | deptry's declaration and digest were corrected; `docs/verification/tr-asset-ci-01b.json` was regenerated through `load_shared_definitions` (not hand-edited) with a revision-history entry; artifact source/hash remain verifiable and unchanged. |
| ECI #52 receives a real target representation and error semantics | Targets must state `abi: "gnu"`/`"musl"` (the ECI Dagger containers are glibc); missing ABI or wrong libc is `unsupported_target` with no fallback. Old frozen selections stay readable as history but fail execution admission on wrong/unknown libc; affected derived documents are re-derived through the actual interfaces. |
| Only this rule and parameter wiring verified; existing artifact/backend evidence reused | No tool downloads or executions; the uv offline lock tests cover the parameter wiring; #8/#17/#20 backend evidence untouched. |

## Evidence

Verified on 2026-10-24 with CPython 3.14.8 (this checkout's locked environment,
uv 0.12.23):

| Evidence | Result |
| --- | --- |
| `tests/test_shared_assets_python.py` | 4 passed — deptry digest/abi re-pinned, musl/unknown-ABI rejections, pure wheels still serve either libc, the old #51 selection stays readable and unchanged. |
| `tests/test_uv_assets.py` | 11 passed — including the new musl-triple lock (really resolved offline), the ABI-less Linux rejection, and the wheel-name libc cross-check (mislabeled release rejected on musl/unknown/Windows, admitted on gnu). |
| Affected suites (`test_assets`, python, uv, native) | 96 passed, 1 skipped. |
| Full suite | 178 passed, 1 skipped (main baseline 176 + the 2 new uv cases) — no regression. |
| Lint / format | `ruff check` clean; `ruff format --check` clean for the tracked tree. |
| `examples/asset_acceptance.py` | The uv acceptance targets now state their real libc (`abi: "gnu"` on Linux), keeping the CI acceptance flow truthful. |

In-repo updated surfaces: `shared_assets/python.json`, `uv_assets.py`,
`tests/test_shared_assets_python.py`, `tests/test_uv_assets.py`,
`examples/asset_acceptance.py`, `docs/assets/python-cli.md`,
`docs/uv-tool-assets.md`, `docs/tool-assets.md`,
`docs/verification/tr-asset-ci-01b.json` (regenerated) and this record. No ECI,
Vesryn, Workflow, Log or host configuration changes; no new installer or platform
framework; full musl artifact support remains out of scope — unsupported targets
are explicitly rejected, which is the required behavior.
