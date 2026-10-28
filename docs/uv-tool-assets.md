# uv tool environments (TR-ASSET-01B)

These APIs build on the [asset contracts](tool-assets.md) and are available
starting with version 0.2.0.

`UvToolBackend` is a thin adapter. **uv** resolves, downloads, verifies hashes,
caches and builds the environment. This package never walks or edits uv's cache, has
no resolver and adds no service, database or scheduler.
uv 0.12.23 is the verified acquisition toolchain; compatibility with other uv
versions is not established by this release's evidence.

## Public entry points

`UvToolBackend` and `UvLock` are exported from `vesryn_tool_runtime`. Their
signatures and types are in the {doc}`generated API reference <autoapi/index>`;
this page keeps the behaviour, the failures and the ownership boundaries.

Only `python` / `uv` releases (`AssetRelease.distribution/backend`) are accepted.
Every operation requires the host's current `AssetPolicy`. Disablement and current
version restrictions apply even to an older frozen selection and an offline hit.

## Two different results

| Call | What it does | Local state |
| --- | --- | --- |
| `prepare` | Builds a venv for **this host** and records an `AssetReceipt` in `AssetIndex`. | Creates `<root>/uv/artifact-<artifact_id>/` |
| `lock` | Runs `uv pip compile --generate-hashes` for the selection's target and returns a `UvLock` for a container (for example Linux). | Only the lock inputs; no environment |

A `UvLock` carries the full transitive requirements with hashes, the uv version, the
`--python-platform`, and the frozen source SHA-256. uv's own reported wheel hash must
equal the definition's `sha256`, otherwise `integrity_mismatch`. A container installs
it with `uv pip install --require-hashes -r`; a Windows `.venv` is never copied.
`tool==version` alone is not treated as locked.

## Behaviour

- **Own environment per artifact.** The directory is keyed by `artifact_id` (asset,
  release, target). Two versions coexist; reuse by another consumer cannot replace
  the environment another selection points at. Project dependencies and the project
  `uv.lock` are never read or written, and the tool is not installed into a consumer
  `.venv`.
- **Frozen environment reuse.** A verified installed environment and its original
  hashed lock are reused, including after uv's cache and source wheels are removed.
  Repeated preparation does not resolve again or delete/recreate that environment.
  A public `lock` call also retains a published environment's lock. A damaged or
  missing published environment reports failure and is not silently replaced;
  hosts own explicit recovery. Unpublished partial attempts remain separate facts.
- **Acquisition vs execution.** `allow_network=False` (default) runs uv `--offline`.
  It is the acquisition permission only. `command` additionally requires
  `scope.admit(spec)` and an unchanged tool contract hash. Preparation never executes
  the tool and installation grants no invocation right. `command` returns the
  verified entry path of that environment; PATH and other installed tools are never
  used, so a different version is never chosen silently. Execution stays in the
  consumer's `ToolAdapter`.
- **Receipt facts.** Success requires uv exit 0, the declared entry file hash, the
  installed package/version equal to the selection, and an `environment_id` that
  hashes the lock, interpreter and installed package set. Failures are recorded as
  `failed`/`unavailable`/`interrupted` receipts and never as installation; the
  receipt document keeps only status and exit code, never uv output.
- **Unsupported hosts** (target OS/architecture differs from this host, or an
  unknown uv platform, or no `target.python`) raise `AssetError("unsupported_target")`
  before anything is touched. Since issue #29 the resolved triple follows the
  target's real C library: Linux requires an explicit `abi` of `gnu` or `musl`
  (`x86_64-unknown-linux-gnu` / `x86_64-unknown-linux-musl`, likewise aarch64);
  an ABI-less Linux target states an unknown libc and is rejected instead of
  silently resolved as GNU. The wheel's own filename is authoritative at
  admission — a `manylinux` (glibc) or `musllinux` name only reaches a Linux
  target with the matching `abi`, so mislabeled declarations or old frozen
  selections cannot execute on the wrong libc.
- **Later reality.** `installed` re-runs `uv pip check` offline and recomputes the
  `environment_id`. A damaged environment is `invalid` and a removed one `missing`;
  a cleared uv cache alone does not break a self-contained environment and is not
  falsely reported either way. It never repairs or downloads.
- Ordinary Catalog queries and `asset_view` still never prepare anything.

## Evidence and limits

[`examples/uv_tool_prepare.py`](../examples/uv_tool_prepare.py) prepares real
vulture 2.16 and 2.14 wheels from PyPI and requests a Linux x86_64 lock. Recorded in
verification record (tr-asset-01b). Tests in
`tests/test_uv_assets.py` use the real uv executable with hand-built wheels.

The #5 joint acceptance adds
real native/Python version calls, offline reuse and public Dagger File/Directory
and Linux lock consumption. Its current CI artifacts identify actual outcomes.

Not verified by the historical #7 evidence: executing the lock inside Dagger/Linux, the ECI consumer, macOS,
and Harness-Python compatibility. Semgrep stays OCI and is not handled by this
backend. Offline preparation of a dependency set relies on uv's cache or
`find_links`; a single `uvx` cache hit is not evidence of permanent offline
availability.

Up: [Documentation](README.md).
