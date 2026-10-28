# vesryn-tool-runtime

Independent Python tool contracts, explicit Provider composition, progressive
discovery, Selection Binding Schema 1, admission and batch invocation. Python 3.14+.

`Registration → Discovery → Binding → Invocation → Execution → Validation → Observation`

This chain describes the Python tool path; Binding and observation are optional.
Host CLI preparation publishes a command list for direct shell use without a
Binding or ToolAdapter; the host makes the entry available on PATH.

Start with [the documentation index](docs/README.md), including the runnable
[quickstart](docs/quickstart.md), [public API](docs/python-api.md),
[discovery field contracts](docs/discovery-contracts.md) and
[CLI asset contracts](docs/tool-assets.md). For release requirements, see
[release readiness criteria](docs/delivery/release-readiness.md) and the
[changelog](docs/changelog.md).

The package owns tools, not workflows. Adapters keep their execution backends;
consumers keep workflow state, checkpoint storage, recovery and domain policy.
Events go through the existing `vesryn_log.EventSink` protocol. Dagger is optional.

Build with `uv build`; install the wheel with its declared dependencies. The
development checkout pins vesryn-log's released source in `tool.uv.sources`.
Versioned artifacts and source provenance are delivered through
[GitHub Releases](https://github.com/dymzz/vesryn-tool-runtime/releases).
Release readiness is recorded separately from successful local verification.
