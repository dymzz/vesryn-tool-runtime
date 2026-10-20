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

- Widen the Log requirement to the compatible `>=0.1.0,<0.2.0` range while preserving the
  existing immutable development source and lock baseline. Tool contracts and Schema 1 are
  unchanged, and the delivered 0.1.0 wheel keeps its recorded SHA-256 until a new wheel is
  built. The binding and admission compatibility conclusion, and the real `JsonlSink`
  regression behind it, are recorded in
  [TR-001](delivery/tr-001-binding-admission.md).
