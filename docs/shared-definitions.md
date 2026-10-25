# Shared asset definitions — RETIRED as a live source (issue #32)

The `shared_assets/*.json` documents and their loader
(`shared_definitions.py`) are retired historical inputs, deleted from the
package. The **single live declaration** is the bundled record seed
(`vesryn_tool_runtime/record_seed.sql`, shipped as a package resource); read
it through the public chain:

```python
from vesryn_tool_runtime import (
    bundled_records,  # seed → ToolAsset/ToolGroup/ToolAccess records
    compose_catalog,  # explicit read-only composition
    open_record_store,  # caller-chosen persistent store
)

store = open_record_store(path)  # path required; ":memory:" supported
store.put_records(bundled_records())  # atomic batch registration
```

Field dictionary: [discovery contracts](discovery-contracts.md). The
temporary bridge for old preparation callers
(`legacy_preparation_definitions`) and its removal are documented in the
[issue #32 delivery record](tasks/vesryn-tool-runtime/P1-unified-tool-registration.md).
