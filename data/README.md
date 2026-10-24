# Data directory

The data home for the record store (issue #27):

- `record_schema.sql` — the frozen DDL: the single authority for the
  six-table layout (three logical entities). Code loads it verbatim; no
  copy exists elsewhere.
- `seed.sql` — the issue's literal example records as INSERT data.
- `records.sqlite3` — the SQLite library built from the frozen schema and
  the seed data; `open_record_store()` opens it by default, and databases
  opened for writing live here too.

Temp scratch, caches and build junk never come here — those belong to
`.cache/`, `.tmp/` and `.artifacts/`.
