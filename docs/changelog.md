# Changelog

## 0.1.0 — extraction candidate

- Migrate authoritative tool contracts, Registry/discovery and Schema validation
  from the current Vesryn worktree, preserving existing tool contract digests.
- Extract engineering-ci Selection Binding Schema 1 identity/integrity checks;
  retain consumer-owned workflow associations and recovery.
- Add independent single/batch invocation and explicit EventSink observations.
- Integrate both consumers through compatibility exports and delegated dispatch.
- No formal release or tag is created. Read [readiness](delivery/tool-runtime-0.1.0.md)
  for verified paths and remaining publication work.

## Unreleased

- Add explicit aria2 native-asset acquisition with pinned downloader provenance,
  verified offline reuse, safe staged extraction and immutable version directories.
  Reuse the common receipt/index and existing File/Directory transport; include
  reviewed OSV/Hyperfine definitions. See [native assets](native-assets.md) and
  [issue #8 delivery](tasks/vesryn-tool-runtime/P0-aria2-native-assets.md).

- Add independent CLI asset definitions/target and version-policy resolution to the
  existing Catalog, plus frozen selection snapshots and a shared, integrity-checked
  local backend receipt/index boundary. Preserve tool/Binding hashes and admission;
  no downloader or installer is introduced. See [asset contracts](tool-assets.md)
  and [issue #6 delivery](tasks/vesryn-tool-runtime/P0-tool-asset-resolution.md).

- Widen the Log requirement to the compatible `>=0.1.0,<0.2.0` range while preserving the
  existing immutable development source and lock baseline. Tool contracts and Schema 1 are
  unchanged, and the delivered 0.1.0 wheel keeps its recorded SHA-256 until a new wheel is
  built. The binding and admission compatibility conclusion, and the real `JsonlSink`
  regression behind it, are recorded in
  [TR-001](delivery/tr-001-binding-admission.md).
