# Shared OCI Asset Declarations (Semgrep & Lychee)

This document details the shared OCI tool declarations delivered under
[Issue #19](https://github.com/dymzz/vesryn-tool-runtime/issues/19) (TR-ASSET-CI-01D / Group D),
child of [Issue #12](https://github.com/dymzz/vesryn-tool-runtime/issues/12).

## Scope and Execution Boundaries

- **Immutable Artifact Identity**: Declarations pin exact SHA-256 digests. Tags or unpinned image
  names are strictly prohibited as source digests.
- **Index vs. Platform Manifest**: Asset releases distinguish multi-arch index digests
  (declared in `source`) from platform-specific image manifests (declared in `sha256` per target).
- **No Local OCI Installer**: `vesryn-tool-runtime` does not implement an OCI puller, image unpacker,
  or container runtime. OCI image acquisition, layer caching, and isolation execution stay natively
  with Dagger (e.g., `dag.container().from_(image)`).
- **Target OS Restriction**: All OCI image releases target `linux` (`x86_64` or `aarch64`).
  Host attempts to select these assets on non-Linux targets (`windows`, `macos`) yield
  `unsupported_target`.
- **Capability Mapping**: Capabilities are associated with existing engineering-ci operations:
  `code.pattern-scan` for Semgrep, and `docs.link-check` for Lychee.

## Asset Declarations

### 1. Semgrep (`semgrep`)

- **Asset ID**: `semgrep`
- **Catalog Revision**: `official-2026-10-24`
- **Associated Tool Capability**: `code.pattern-scan`
- **Upstream Repository**: `docker.io/semgrep/semgrep`
- **Upstream Release**: `1.99.0`
- **Multi-Arch Index Digest**: `sha256:ae27024c16f7848cdbfd49c24ed0b78b13f13b85fcd7b87c679aaa8b0c0dce98`
- **Entrypoint**: `semgrep`
- **Platform Releases**:
  - `linux/x86_64` (glibc):
    - Digest: `sha256:374d5a678b58e9ba3ef291ce37ffa836f69150a2360c78f02dca7a07bc42fb7d`
    - Source: `docker.io/semgrep/semgrep@sha256:ae27024c16f7848cdbfd49c24ed0b78b13f13b85fcd7b87c679aaa8b0c0dce98`
  - `linux/aarch64` (glibc):
    - Digest: `sha256:08f1c44024049d1a104f57203dab60b3579f17a12fe87bac7bb60130bbc46bfc`
    - Source: `docker.io/semgrep/semgrep@sha256:ae27024c16f7848cdbfd49c24ed0b78b13f13b85fcd7b87c679aaa8b0c0dce98`
- **engineering-ci Mapping**:
  - Module: `.dagger/src/engineering_ci/semgrep.py`
  - Consumer functions: `semgrep_scan`, `semgrep_report`, `semgrep_artifacts`
  - Dagger container consumption: `dag.container().from_("docker.io/semgrep/semgrep@sha256:374d5a678b58e9ba3ef291ce37ffa836f69150a2360c78f02dca7a07bc42fb7d")`

### 2. Lychee (`lychee`)

- **Asset ID**: `lychee`
- **Catalog Revision**: `official-2026-10-24`
- **Associated Tool Capability**: `docs.link-check`
- **Upstream Repository**: `docker.io/lycheeverse/lychee`
- **Upstream Release Tag**: `lychee-v0.18.0` (Git commit `1780aa0daa70462e296f9811e06178f13fd945db`)
- **Docker Hub Tag Reference**: `sha-1780aa0` (due to upstream tag matching convention)
- **Multi-Arch Index Digest**: `sha256:83d7644b4b633943c94baa15ddd274637b9ec49f746ab2ce1c77c33be1e680a5`
- **Entrypoint**: `lychee`
- **Platform Releases**:
  - `linux/x86_64` (musl):
    - Digest: `sha256:606c60a7f61ab802297973d1bd9a429c88c4b99596a23bfe34e63a46b6d40fc8`
    - Source: `docker.io/lycheeverse/lychee@sha256:83d7644b4b633943c94baa15ddd274637b9ec49f746ab2ce1c77c33be1e680a5`
  - `linux/aarch64` (musl):
    - Digest: `sha256:b1be296f112676caac52748c7f692eacde9a26fa23f8715b5662af9ad7dd451c`
    - Source: `docker.io/lycheeverse/lychee@sha256:83d7644b4b633943c94baa15ddd274637b9ec49f746ab2ce1c77c33be1e680a5`
- **engineering-ci Mapping**:
  - Module: `.dagger/src/engineering_ci/lychee.py`
  - Consumer functions: `lychee_check`, `lychee_report`, `lychee_artifacts`
  - Dagger container consumption: `dag.container().from_("docker.io/lycheeverse/lychee@sha256:606c60a7f61ab802297973d1bd9a429c88c4b99596a23bfe34e63a46b6d40fc8")`

## Consumption Guide

To read and assemble these definitions in consumer projects:

```python
from vesryn_tool_runtime import (
    Catalog,
    ExecutionPolicy,
    TargetPlatform,
    ToolSpec,
    load_shared_definitions,
    register_shared_definitions,
)

# 1. Pure read without side effects
records = load_shared_definitions("oci.json")

# 2. Register real consumer capability adapters
catalog = Catalog()
catalog.register(ToolSpec("code.pattern-scan", {}, {}, effect="check"), semgrep_adapter)
catalog.register(ToolSpec("docs.link-check", {}, {}, effect="check"), lychee_adapter)

# 3. Explicit assembly into Catalog
register_shared_definitions(catalog, records)

# 4. Target platform resolution
linux_target = TargetPlatform(os="linux", arch="x86_64", abi="gnu")
view = catalog.asset_view("code.pattern-scan", target=linux_target, policy=ExecutionPolicy())
# view.selectable == True
# view.release.sha256 == "374d5a678b58e9ba3ef291ce37ffa836f69150a2360c78f02dca7a07bc42fb7d"
```

## Verification Status

- **Semgrep 1.99.0**: Verified by pulling and executing inside a live Dagger Engine container,
  verifying `--version` output `1.99.0`.
- **Lychee 0.18.0**: Upstream release metadata, Git tag, commit SHA, multi-arch index, and
  platform manifest digests verified against Docker Hub registry API. Execution status is retained
  as unexecuted/ready declaration to reflect exact state per acceptance guidelines.
