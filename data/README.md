# Data directory

Committed artifacts for the record store (issue #27), nothing runtime:

- `record_schema.sql` — the frozen DDL: the single authority for the
  six-table layout (three logical entities). Code loads it verbatim;
  no copy exists elsewhere.
- `seed.sql` — the issue's literal example records as INSERT data.
- `records.sqlite3` — the SQLite library built from the frozen schema and
  the seed data.

Runtime databases opened by `open_record_store` go to temp locations,
never into this directory.
