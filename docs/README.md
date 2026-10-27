# Documentation

- [Quickstart](quickstart.md): installation, complete public chain, runnable example.
- [Public Python API](python-api.md): contracts, discovery, binding, batch dispatch, host tools, and usage patterns.
- [Architecture and ownership](architecture.md): migrated code and consumer boundaries.
- [Failure and observation semantics](failure-semantics.md): outcomes, validation and EventSink.
- [Provider and Dagger integration](providers.md): explicit loading and execution boundaries.
- [Discovery field contracts](discovery-contracts.md): ToolAsset/ToolGroup/ToolAccess field dictionary and SQLite schema.
- [CLI asset contracts & host tools](tool-assets.md): definitions, frozen selections, ABI/OCI constraints, and host tools lifecycle.
- [Native asset acquisition](native-assets.md): explicit aria2 preparation, repeated verification and File/Directory delivery.
- [uv tool environments](uv-tool-assets.md): thin uv adapter, per-artifact environments and Linux lock description.
- [Dagger package delivery](dagger.md): fixed-revision wheel delivery for executors.
- [Consumer migration](consumers.md): compatibility paths and development source inputs.
- [Release readiness criteria](delivery/release-readiness.md): authoritative C1–C8 acceptance standards.
- [Changelog](changelog.md): versioned changes and compatibility notes.
- [Architecture decisions](adr/persist-installation-provenance.md): standalone ADRs linked to specifications via Sphinx-Needs.
- [Test evidence](test-evidence.md): test cases converted from a real JUnit report, linked to the specifications they verify.
- [Semgrep OCI execution evidence](verification/tr-asset-ci-01d-semgrep/README.md): unabridged Dagger native execution capture.

```{toctree}
:hidden:
:glob:
:maxdepth: 2

*
autoapi/index
adr/*
delivery/*
verification/tr-asset-ci-01d-semgrep/README
```

## Build this manual

The test evidence is converted first, from a report the project's own test run
writes. Only the traced test file is executed, and the report is kept:

```console
uv run --locked pytest tests/test_host_tools.py -k cached_replacement_is_not_installation_proof --junitxml=.tmp/junit.xml
uv run --locked test-reports build needs .tmp/junit.xml --output .tmp/test-needs.json --config docs/ubproject.toml --commit "$(git rev-parse HEAD)"
```

The conversion reads the JUnit-property mapping from `docs/ubproject.toml`;
`--link-property` would replace that whole table, so it is not given on the
command line.

Use the Runtime-prepared Sphinx CLI with the pinned MyST/Needs plugins described
in [Python CLI preparation](tool-assets.md#python-cli-plugins-in-the-same-tool-environment).
Run from the repository root in the target shell where that registered entry
resolves:

```console
sphinx-build -b html -n -W --keep-going -d .tmp/docs/doctrees docs .tmp/docs/html
```

The same HTML build writes `README.html` and `needs.json` under `.tmp/docs/html`.
Project/version metadata comes from `pyproject.toml`. Standalone ADRs live under
`docs/adr/<imperative-verb-phrase>.md` and wrap their full Nygard decision body
(`Context`, `Decision`, `Consequences`) inside a MyST `:::{adr}` colon fence so
`needs.json` exports the complete decision content (`content`).

Each ADR maintains its authoritative status solely in `:status:` (`proposed`,
`accepted`, `rejected`, `superseded`, or `deprecated`, enforced as non-nullable by
`needs_types["adr"]["fields"]["status"]` in `docs/conf.py`) and links to
specifications through `:decides:` (for example,
[Persist Installation Provenance](adr/persist-installation-provenance.md) decides
`SPEC_TR_MAIN_ARTIFACT_PROOF` in [host tools](tool-assets.md#main-artifact-provenance)).
Clarifications that preserve an existing decision update the ADR in place;
changes that replace an accepted decision create a new ADR with `:supersedes:`
targeting the prior `ADR_` ID and set the old ADR's `:status:` to `superseded`.
Need references, target types, and field schemas are checked by Sphinx-Needs;
`-n` alone does not guarantee these semantics. `-W` makes their warnings fail the
build. Planning documents under `superpowers/` are not part of this public manual;
generated files stay in the ignored temporary directory. Existing Mermaid fences
render as source text in HTML and as diagrams on GitHub.

Up: [Repository](https://github.com/dymzz/vesryn-tool-runtime).
