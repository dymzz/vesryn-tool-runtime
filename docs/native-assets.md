# Native assets through aria2

This is the public handoff for [issue #8](https://github.com/dymzz/vesryn-tool-runtime/issues/8),
TR-ASSET-01C, based on the [asset contracts](tool-assets.md) merged in source
`f60eadd`. These additions are delivered in 0.2.0 and are not present in the
original 0.1.0 wheel. No consumer pin is changed here.

## Public entry points

`Aria2Source`, `Aria2NativeBackend` and `NativeAssetDelivery` are exported from
`vesryn_tool_runtime`. Their signatures and types are in the
{doc}`generated API reference <autoapi/index>`; this page keeps the behaviour,
the failures and the ownership boundaries.

These names are exported from `vesryn_tool_runtime`. Constructing a backend does
not prepare anything. The host explicitly calls `prepare` after selecting through
the existing Catalog. Pass the **current** acquisition policy on every preparation
and delivery, including reuse: a frozen old selection cannot override current
disablement or an allowed-version constraint. Acquiring a tool, passing verification,
or obtaining its path never admits a business invocation. The consumer's existing
ToolAdapter, Binding and explicit host Scope retain execution ownership.

On Windows, a versioned archive entry can exceed 260 characters. Its consumer
Adapter should pass the program explicitly, for example
`subprocess.run([str(delivery.executable), "--version"], executable=str(delivery.executable))`.
Leaving Windows `CreateProcessW.lpApplicationName` implicit retains a MAX_PATH
limit even with an extended path prefix. The acceptance example verifies explicit
launch of both real Hyperfine versions; no global registry setting is changed.

The backend supports raw ELF/PE binaries, ZIP, and tar archives (`.tar`, `.tar.gz`,
`.tgz`, `.tar.xz`, `.tar.bz2`, `.tar.zst`), identified by the trusted source URL's
suffix. Other suffixes denote a raw binary. Initial targets are Linux and Windows
on x86_64, aarch64 and x86. The selected entry's ELF/PE machine and OS must match
the explicit target's binary format. Linux provenance and ABI suitability remain publisher declarations bound to the
artifact hash; this check does not prove a runner has a compatible dynamic loader.
Unsupported targets fail before acquisition. Preparing a Linux payload on Windows
is supported; the backend does not execute it or claim host readiness.

## Prepare aria2 independently

Supply an absolute executable path, its expected version, and its executable-file
SHA-256. There is no PATH fallback or self-bootstrap through the candidate Runtime.
Before a network download, the backend re-hashes that executable and checks the
actual `aria2 --version`. Hosts can use a separately delivered CI/CD toolchain.
No runtime download or execution of aria2 is needed for a verified offline hit or
explicit `source_artifact` restoration.

The Windows verification used aria2 1.37.0 from the
[official Release](https://github.com/aria2/aria2/releases/tag/release-1.37.0):

- Archive: `aria2-1.37.0-win-64bit-build1.zip`, SHA-256
  `67d015301eef0b612191212d564c5bb0a14b5b9c4796b76454276a4d28d9b288`.
- Hash authority: the corresponding
  [WinGet installer manifest](https://github.com/microsoft/winget-pkgs/blob/master/manifests/a/aria2/aria2/1.37.0/aria2.aria2.installer.yaml).
  The older GitHub Release has no asset digest field. This is a separate package
  record cross-check, not a claim of a publisher signature.
- Extracted `aria2c.exe` SHA-256:
  `be2099c214f63a3cb4954b09a0becd6e2e34660b886d4c898d260febfe9d70c2`.

These are evidence for the verified Windows toolchain, not hashes of Linux aria2
binaries. CI/CD owners review their target's initial source/hash and changes.
The library neither downloads adjacent checksum files to establish first trust
nor registers arbitrary tools found on the machine.

## Acquisition and repeated verification

Use `AssetIndex(asset_root(explicit_configuration))` for a configured persistent
root. No developer-machine path is built into the package. Layout:

```text
<root>/downloads/sha256-<distribution-sha256>/artifact
<root>/downloads/.prepare-<unique>/...   # temporary; removed on failure/return
<root>/locks/...                       # explicit acquisition/publication locks
<root>/native/asset-<id>/<full-target>/version-<version>/<distribution-sha256>/...
<root>/index.json                      # the existing shared AssetIndex
```

`prepare` follows these steps:

1. Check current policy/target and refuse a corrupt shared index.
2. Serialize publication for this artifact; serialize source acquisition by SHA-256.
3. Re-hash an existing distribution. With no distribution, use an explicitly supplied
   `source_artifact` or, only with `allow_network=True`, download using pinned aria2
   into a unique controlled staging directory.
4. aria2 checks the frozen SHA-256; Runtime independently hashes the actual bytes.
   The command disables user configuration/netrc, RPC/DHT, torrent/metalink following,
   automatic file renaming and overwriting, and keeps certificate verification on.
5. Derive every expected regular-file hash from that verified distribution; reject
   unsafe archive names, links, special files, duplicate/case-alias names, excessive
   member counts/unpacked bytes, ambiguous/missing entrypoints and wrong binary targets.
6. For a miss, use stdlib `zipfile` or `tarfile` with its explicit `data` filter in
   fresh staging, verify the resulting files, and rename the complete directory to
   its final immutable version path. An existing version directory is verified in
   place; it is never overwritten or automatically repaired.
7. Record the actual outcome using the same `AssetReceipt`/`AssetIndex` as uv.

Both `prepare` reuse and read-only `delivery` re-hash the cached distribution,
derive the expected manifest again, and compare **all** published file bytes and
the exact file set. A self-consistent `index.json` or forged receipt cannot replace
the trusted distribution hash. An external cache restore uses this identical path;
the cache's own metadata is not authority. Retain the source distribution for
offline verification; an extracted directory alone is insufficient for this backend.

`max_bytes` bounds a retained distribution and declared unpacked content; network
downloads run with an overall timeout and stage outside published directories.
This is not a streaming network quota or a defense against a hostile filesystem
owner changing files during verification/import. Hosts own and protect their
configured root and keep published payloads immutable.

Download interruption, bad bytes, extraction failures and unavailable backends
return a non-passed receipt and cannot replace a verified installation. aria2's
nonzero exit code is preserved (for example, `failed/17` stays `failed/17`).
Timeout/interruption is `interrupted` with no invented exit status; offline absence
is `unavailable` with reason `offline_missing`. The index keeps an older installation
and records the new attempt independently. Inspect `receipt.outcome.reason` for
the safe operational reason; the persisted A receipt intentionally omits diagnostics.
Corrupt-index and lock-timeout errors remain explicit `AssetError`s. No automatic
retry, repair, eviction, global PATH update or deletion of another version occurs.

Additional stable reason codes are `unsafe_archive`, `invalid_archive`,
`entrypoint_missing`, `entrypoint_ambiguous`, `artifact_target_mismatch`,
`asset_too_large`, `backend_integrity_mismatch`, `backend_version_mismatch`,
`backend_version_check_failed`, `unsupported_source`, `download_failed`,
`offline_missing`, `backend_unavailable`, and `backend_interrupted`. Existing A codes
retain their meaning. `delivery` raises on missing/invalid facts and performs no
download, index mutation, subprocess call or Dagger startup.

## OSV and Hyperfine consumer example

[Reviewed definitions](../examples/native-assets.json) contain five exact artifacts:

| Program | Target | Distribution SHA-256 |
| --- | --- | --- |
| Hyperfine 2.0.0 | Linux x86_64/gnu | `ae2beda2ac99c098427e4f755244552daf20e514422889cca6d44421e2d93c87` |
| Hyperfine 1.20.0 | Linux x86_64/gnu | `63ad53934062118f5b0be11785e0bb1603d4b91667d1921f2fd8df9a8712040a` |
| Hyperfine 2.0.0 | Windows x86_64/msvc | `3dec51acee1060908e67948838d6bc0a7aacde0774acebfa4afb220dcf0bc078` |
| Hyperfine 1.20.0 | Windows x86_64/msvc | `2508c549b049b1d4342d08edc1cb42bfac169082b6e3069431b5bab9822dbb32` |
| OSV Scanner 2.6.0 | Linux x86_64 | `ca69b3d3cd08f889a49dc0a383122f71cc528b83803671df5fd874d97485b108` |

The hashes were checked against the publishers' Release asset metadata on
2026-10-23: [Hyperfine 2.0.0](https://github.com/sharkdp/hyperfine/releases/tag/v2.0.0),
[Hyperfine 1.20.0](https://github.com/sharkdp/hyperfine/releases/tag/v1.20.0), and
[OSV 2.6.0](https://github.com/google/osv-scanner/releases/tag/v2.6.0).
JSON provenance retains Release/asset IDs and exact official URLs. These examples
are explicit declarations for supply-chain review, not an automatic remote catalog
or changes to either consumer's source of truth.

After installing the candidate wheel, run
`examples/native_asset_delivery.py` with `--asset hyperfine --version 2.0.0
--os linux --arch x86_64 --abi gnu`, or `--asset osv-scanner --version 2.6.0
--os linux --arch x86_64`. Both require explicit `--root`, `--aria2`,
`--aria2-version`, `--aria2-sha256` and `--policy-revision`; add `--allow-network`
for acquisition or `--source-artifact` for restoration. Without either, only a
valid retained artifact is reusable. There is no business execution in this sample.

The sample's `dagger_directory(dag, delivery)` uses the existing
`dag.host().directory(..., include=[verified file paths])`;
`dagger_file(dag, delivery)` returns its `.file(delivery.entry)`. Consumers can
import a read-only snapshot into their existing graph, for example:

```python .skip
payload = dagger_file(dag, backend.delivery(selection, policy=current_policy))
container = container.with_file("/opt/tools/hyperfine", payload, permissions=0o755)
```

Choose a container matching the delivery's target and loader requirements. Explicit
permissions preserve Linux executable mode when the acquisition host is Windows.
Importing a snapshot does not mount a cross-repository writable cache. Native local
Installed state says nothing about other runners. No Dagger SDK becomes a base
dependency, and no scan, benchmark or new execution/transport protocol is introduced.

Directed results and their limits are recorded in the issue #8 delivery history.
