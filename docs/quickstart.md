# Quickstart

Python 3.14+ is required. Build `vesryn-tool-runtime==0.1.0` with `uv build` and
install its wheel together with `jsonschema==4.26.0` and `vesryn-log==0.1.0`.
If using the private Git source, the development manifest pins vesryn-log to
`030c5a8edf820588e29f53803b6baaf53b1f6e57`; supply Git access through your existing
credential mechanism. Wheels declare ordinary versioned dependencies, without
checkout paths or Git credentials. Supply an approved vesryn-log wheel when using
an offline wheelhouse. Consumers do not need Vesryn, engineering-ci or Dagger.
Source distributions include documentation, the example and independent tests
using the build backend's documented [source inclusion settings](https://docs.astral.sh/uv/concepts/build-backend/#file-inclusion-and-exclusion).

Run `python examples/direct_tool.py`. It registers a real Python adapter, discovers
its contract, freezes a selection and invokes it through current scope. To record
events, pass a public `vesryn_log.JsonlSink(authorized_path)` as `event_sink`.

For development: `uv sync --locked`, `uv run --locked pytest`,
`uv run --locked ruff check .`, `uv run --locked ruff format --check .`.
CI delegates lint/format/tests to engineering-ci's fixed v0.6.7 commit
`0f74b2f776796b9db83f7a61c0849e504afdbea0` through Dagger. `dagger check` requires
an engine and the existing `ENGINEERING_CI_READ_TOKEN` Secret for the approved
private Git dependency. `dagger.toml` resolves it from the environment; tokens
are never written to source. The separate package job verifies a wheel install.

Direct invocation performs no workflow generation, persistence, retry or backend
selection. The host authorizes filesystem paths and owns any durable execution
intent. A Binding's digest verifies integrity; current permissions still apply.
