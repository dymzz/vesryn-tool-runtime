# Dagger package delivery

Installed Python consumers use the public Python API. Cross-repository Dagger
executors can obtain this package through the independent `api/` module's
`python-package` function, which returns a `dagger.File` containing the wheel.
Pin the module source and `pin` to the same accepted full Git commit:

```json
{
  "name": "vesryn-tool-runtime",
  "source": "github.com/dymzz/vesryn-tool-runtime/api@FULL_COMMIT_SHA",
  "pin": "FULL_COMMIT_SHA"
}
```

Call `dag.vesryn_tool_runtime().python_package()` from the consuming Dagger
module and install the returned wheel with its declared dependencies. The module
builds only its own filtered source, README and license. It installs no runtime
dependencies and needs no Git credential inside its build container. The Dagger
client still needs access to the module repository. Consumers supply
vesryn-log separately through its existing public package delivery interface.
An explicit optional `source` Directory builds an authorized development checkout
through the same interface; no adjacent source directory is inferred.

For an explicit local development check:

```sh
dagger api call --load-module ./api python-package export --path ./dist/vesryn_tool_runtime-0.4.0-py3-none-any.whl
```

This interface delivers a Python artifact. Tool execution, scope, binding and
event recording retain the documented Python contracts.

## Log dependency

The current wheel requires `vesryn-log>=0.1.0,<0.2.0`. The development source
and lock select the immutable Log commit documented in the [quickstart](quickstart.md).
Consumers supply a compatible published distribution or approved wheelhouse and
use normal dependency resolution. Historical wheel identities remain in their
respective release records.
