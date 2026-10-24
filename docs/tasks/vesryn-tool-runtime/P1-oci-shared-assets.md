# TR-ASSET-CI-01D — issue #19 delivery record

Source: [issue #19](https://github.com/dymzz/vesryn-tool-runtime/issues/19), stage D of
[issue #12](https://github.com/dymzz/vesryn-tool-runtime/issues/12). Delivery record created from
the fetched issue #19 body and engineering-ci contract alignment.

Baseline verified locally: branch `main`, commit `36672388624fd3008117d3b79c9819790d21a602`,
package version 0.2.0. The package version stays 0.2.0; no release, tag or publication is performed.
Existing user changes to `AGENTS.md`, `.gitignore`, `.codex/` and `unregistered/` remain outside
this implementation.

Branch and PR: `codex/issue-19-oci-shared-assets`, delivering exclusively the Group D files
stipulated in [Shared asset definitions](../../shared-definitions.md).

## Delivery Scope and File Ownership

Group D owns exclusively:
- Definition data: `src/vesryn_tool_runtime/shared_assets/oci.json`
- Verification tests: `tests/test_shared_assets_oci.py`
- Exclusive documentation: `docs/assets/oci.md`
- Delivery record: `docs/tasks/vesryn-tool-runtime/P1-oci-shared-assets.md`
- Verification evidence: `docs/verification/tr-asset-ci-01d.json`

Common files (`src/vesryn_tool_runtime/__init__.py`, `shared_definitions.py`, `pyproject.toml`,
`docs/shared-definitions.md`, `docs/README.md`, `docs/changelog.md`) are not modified.

## Artifact Identity and Immutable Digests

Both assets pin exact multi-arch index digests in `source` and platform-specific image manifest
digests in `sha256`. Tags are never used as digests.

1. **Semgrep (`semgrep`)**:
   - Upstream: `docker.io/semgrep/semgrep:1.99.0`
   - Associated capability: `code.pattern-scan`
   - Multi-arch index digest: `sha256:ae27024c16f7848cdbfd49c24ed0b78b13f13b85fcd7b87c679aaa8b0c0dce98`
   - Platform manifests:
     - `linux/amd64` (glibc): `sha256:374d5a678b58e9ba3ef291ce37ffa836f69150a2360c78f02dca7a07bc42fb7d`
     - `linux/arm64` (glibc): `sha256:08f1c44024049d1a104f57203dab60b3579f17a12fe87bac7bb60130bbc46bfc`
   - Entrypoint: `semgrep`
   - engineering-ci contract: `.dagger/src/engineering_ci/semgrep.py` (`semgrep_scan`, `semgrep_report`, `semgrep_artifacts`)
   - Native Dagger consumption: Verified live via Dagger Engine.

2. **Lychee (`lychee`)**:
   - Upstream: `docker.io/lycheeverse/lychee:sha-1780aa0` (Git release tag `lychee-v0.18.0` on commit `1780aa0daa70462e296f9811e06178f13fd945db`)
   - Associated capability: `docs.link-check`
   - Multi-arch index digest: `sha256:83d7644b4b633943c94baa15ddd274637b9ec49f746ab2ce1c77c33be1e680a5`
   - Platform manifests:
     - `linux/amd64` (musl): `sha256:606c60a7f61ab802297973d1bd9a429c88c4b99596a23bfe34e63a46b6d40fc8`
     - `linux/arm64` (musl): `sha256:b1be296f112676caac52748c7f692eacde9a26fa23f8715b5662af9ad7dd451c`
   - Entrypoint: `lychee`
   - engineering-ci contract: `.dagger/src/engineering_ci/lychee.py` (`lychee_check`, `lychee_report`, `lychee_artifacts`)
   - Native Dagger consumption: Declaration verified against registry metadata; execution state retained as unexecuted/ready declaration.

## Architectural and Operational Invariants

- **No OCI Installer Backend**: `vesryn-tool-runtime` introduces no image downloader, local tarball
  extractor, or container runtime backend. Image pulling, layer caching, and sandboxing are handled
  entirely by Dagger.
- **Platform Invariants**: Non-Linux platforms (`windows`, `macos`) are rejected as `unsupported_target`
  by `Catalog.asset_view`. OCI tools execute exclusively within Linux container environments.
- **Explicit Assembly**: Asset definitions are loaded through `load_shared_definitions("oci.json")`
  and bound to capabilities with `register_shared_definitions(catalog, definitions)`. Capabilities
  must be registered with an adapter first; missing tools are rejected as `unregistered_tool`.

## Directed Acceptance and Verification

Original implementation results reported on 2026-10-24 with CPython 3.14.8 are listed below. The Semgrep execution row now links a separate follow-up capture; the historical Python test results were not rerun for this evidence-only change:

| Directed evidence | Result |
| --- | --- |
| Group D test suite | `tests/test_shared_assets_oci.py` passed (7/7 tests). |
| Full regression suite | 159 passed, 1 skipped (0 regressions). |
| Static analysis & format | `uv run ruff check` and `uv run ruff format --check` clean. |
| Live Dagger native execution | The original result in `docs/verification/tr-asset-ci-01d.json` lacks a native run locator. Separate follow-up [raw Dagger evidence](../../verification/tr-asset-ci-01d-semgrep/README.md) records the same pinned Linux amd64 image, one actual execution of `semgrep --version`, stdout `1.99.0`, and container/CLI exit codes 0. Image acquisition was cached; no new pull, scan or other platform is claimed. |
| Upstream provenance verification | Docker Hub registry index and platform manifests verified for Semgrep and Lychee. Lychee commit SHA `1780aa0daa70462e296f9811e06178f13fd945db` mapped to tag `sha-1780aa0`. |

The offline OCI tests check declarations and selection only. Their success is not live Dagger evidence. The separate follow-up preserves the original report and captures the query, native response, native diagnostics and process record with SHA-256 references.
