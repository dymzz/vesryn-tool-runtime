# vesryn-tool-runtime

Independent Python tool contracts, explicit Provider composition, progressive
discovery, Selection Binding Schema 1, admission and batch invocation. Python 3.14+.

`Registration → Discovery → Binding → Invocation → Execution → Validation → Observation`

Start with [the documentation index](docs/README.md), including the runnable
[quickstart](docs/quickstart.md), [public API](docs/python-api.md) and
[0.2.0 readiness and joint acceptance](docs/tasks/vesryn-tool-runtime/P0-local-tool-assets.md).

The package owns tools, not workflows. Adapters keep their execution backends;
consumers keep workflow state, checkpoint storage, recovery and domain policy.
Events go through the existing `vesryn_log.EventSink` protocol. Dagger is optional.

Build with `uv build`; install the wheel with its declared dependencies. The
development checkout pins vesryn-log's released source in `tool.uv.sources`.
Versioned artifacts and source provenance are delivered through
[GitHub Releases](https://github.com/dymzz/vesryn-tool-runtime/releases).
Release readiness is recorded separately from successful local verification.
