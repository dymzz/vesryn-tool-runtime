# Data directory

The repository's database home for the record store (issue #27):

- `records.sqlite3` — the demo library built from the frozen package schema
  and seed; tests open it by explicit path.

The frozen DDL and the seed records ship INSIDE the package as resources
(`vesryn_tool_runtime/record_schema.sql`, `record_seed.sql`), read through
`importlib.resources`, so independent installs need no source checkout.
Writable database locations are always supplied explicitly by the caller —
nothing resolves a default from the install directory. Temp scratch, caches
and build junk belong to `.cache/`, `.tmp/` and `.artifacts/`, never here.
