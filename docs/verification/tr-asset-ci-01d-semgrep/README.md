# Semgrep OCI entry-point execution evidence

This capture supplements Runtime #12 / #19. It does not reconstruct the
unlocated original run reported in `../tr-asset-ci-01d.json`.

- Run marker: `semgrep-20261024T032747Z`.
- Runtime declaration baseline: `3902efcb2154c82caf95c8d7d449f7268d68f6d1`
  (released v0.3.0), `shared_assets/oci.json`.
- Selected platform: `linux/amd64` (Runtime target `linux/x86_64`).
- Image: `docker.io/semgrep/semgrep@sha256:374d5a678b58e9ba3ef291ce37ffa836f69150a2360c78f02dca7a07bc42fb7d`.
- Tool command: `semgrep --version`; no repository is mounted and no scan runs.
- Native Dagger response: stdout `1.99.0\n`, container exit code `0`.
  Tool stderr contains Semgrep's update notice; it is retained in full.
- Dagger CLI process exit code: `0`, no timeout.
- Native diagnostics identify client/server `v1.0.0-beta.16`, server commit
  `2d95ef98`, and the local Docker engine connection.

## Read the original records

1. [query.graphql](query.graphql) is the complete query actually submitted.
2. [dagger.stdout.json](dagger.stdout.json) is the unabridged Dagger query response,
   including container stdout, stderr and exit code.
3. [dagger.stderr.log](dagger.stderr.log) is Dagger's unabridged native progress and
   debug output, including the selected image, engine, query and execution spans.
4. [process.json](process.json) records the actual CLI arguments, working location,
   timestamps, process exit and timeout state. Its local paths describe this capture;
   they are not installation requirements or reusable configuration.
5. [sha256.json](sha256.json) records the hashes of these four captured files.

Native span IDs in `dagger.stderr.log`, scoped to this capture:

| Boundary | Span ID | Observed result |
| --- | --- | --- |
| `POST /query` | `6eba22ea55eb6b1f` | DONE |
| `Container.from` | `304126b519543ce1` | CACHED: image reuse, not a new pull |
| outer `withExec semgrep --version` | `2648be5768aa8ae7` | DONE, not CACHED |
| `exec.processRun` | `381ea8c820552de1` | DONE, 14.0 seconds |

The log contains one actual `exec.processRun` span. Repeated `withExec`, stdout,
stderr and exit-code spans are lazy graph/result boundaries, not additional tool
executions. The query's run marker distinguishes this execution from earlier
cached commands. No hosted trace URL was provided; the setup URL in the log is
not a run locator. Read the captured native log instead.

## Reproduce only when necessary

From this directory, using an already authorized local Docker/Dagger environment:

```powershell
$env:FORCE_DARK_MODE = '1'
dagger --progress plain --debug query -M --doc query.graphql
$daggerExit = $LASTEXITCODE
exit $daggerExit
```

`FORCE_DARK_MODE` was set only in the calling process for the repository's known
Windows noninteractive startup issue. `-M` disables module loading. This command
needs no private repository credential or Python Provider. Keep future capture
files separate; do not overwrite this run or treat a future cache hit as new execution.

## Acceptance boundary

The native records prove that the declared Linux amd64 digest and Semgrep entry
point were consumed by Dagger and returned the stated version. They do not prove
an engineering-ci scan, all OCI platforms, Lychee execution, production Binding,
security findings, or an installation receipt on the host.

`test_semgrep_selection_retains_pinned_oci_source_and_entrypoint` remains an
offline selection test. Its success does not replace this execution evidence.
The original `tr-asset-ci-01d.json` is retained unchanged as historical reported
evidence; this capture is an explicitly separate follow-up.
