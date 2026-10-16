# Upstream observations

## uv 0.12.23 / Windows restricted execution: Python trampoline and credential access

- Seen: 2026-10-16. Status: environment limitation; no upstream defect asserted.
- Evidence: the pre-existing free-threaded `.venv/Scripts/python.exe` failed with
  `uv trampoline failed to spawn Python child process: permission denied` in the
  restricted executor. The ordinary CPython 3.14.3 executable ran successfully.
- A pinned private Git dependency fetch additionally reported unavailable
  `wincredman` credential persistence and disabled terminal authentication.
- Workaround: use an ordinary CPython test environment in `.test-tools`; verify
  the exact released vesryn-log commit from the local Git object as a wheel, and
  use the normal approval path for credential/engine access. No third-party code,
  auth settings or personal credential files are modified.

## Dagger 1.0.0-beta.16: optional Directory annotation must carry Ignore externally

- Seen: 2026-10-16. Status: observed SDK integration pitfall, no SDK defect asserted.
- `Source = Annotated[Directory, Ignore(EXCLUDES)]` followed by a parameter of
  `Source | None` did not preserve exclusions in the actual generated argument.
  The host attempted to upload `.dagger/sdk/runtime/go.sum` and failed with EOF.
- `Annotated[Directory | None, Ignore(EXCLUDES)]` produced the explicit expected
  exclude list in the actual Dagger trace and the catalog invocation succeeded.
- The consumer now uses the latter spelling. Discovery and real shared-tool
  execution passed afterward; no SDK, Engine or generated code is patched.

The extracted introspection code also retains the existing Vesryn workaround
using `dagger api query --doc` to leave caller stdin intact. Its original Engine
observations remain in the consumer's `.agent/upstream-observations.md`.

## uv 0.12.23: cache-in-source warning does not inspect uv_build inclusion rules

- Seen: 2026-10-16. Status: observed diagnostic limitation; not a packaging defect.
- Builds warn that the repository-local `.test-tools/uv-cache` may enter a
  distribution. This project uses the default module root and explicit bounded
  source includes; inspection of the actual wheel and sdist confirmed that the
  cache, `.test-tools`, `.codex` and virtual environments were absent.
- The local cache is needed by the restricted executor. Artifacts are inspected
  directly; no upstream code or global cache configuration is modified.
