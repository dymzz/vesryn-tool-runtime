CREATE TABLE tool_asset (
    tool_id    TEXT NOT NULL PRIMARY KEY,
    name       TEXT NOT NULL CHECK (length(name) > 0),
    provider   TEXT NOT NULL CHECK (provider IN ('uv', 'github-release', 'oci')),
    package    TEXT,
    entrypoint TEXT NOT NULL CHECK (length(entrypoint) > 0)
);
CREATE TABLE tool_release (
    tool_id         TEXT NOT NULL REFERENCES tool_asset (tool_id),
    version         TEXT NOT NULL CHECK (length(version) > 0),
    platform_os     TEXT,
    platform_arch   TEXT,
    platform_abi    TEXT,
    platform_python TEXT,
    source          TEXT NOT NULL CHECK (length(source) > 0),
    digest_type     TEXT NOT NULL CHECK (digest_type IN ('sha256')),
    digest          TEXT NOT NULL CHECK (
        length(digest) > 0
        AND (digest_type != 'sha256' OR (
            length(digest) = 64 AND digest NOT GLOB '*[^0-9a-f]*'
        ))
    ),
    CHECK ((platform_os IS NULL) = (platform_arch IS NULL)),
    CHECK (
        platform_os IS NULL
        OR (length(platform_os) > 0 AND length(platform_arch) > 0)
    ),
    CHECK (platform_abi IS NULL OR length(platform_abi) > 0),
    CHECK (platform_python IS NULL OR length(platform_python) > 0)
);
CREATE UNIQUE INDEX tool_release_identity
    ON tool_release (
        tool_id, version,
        coalesce(platform_os, ''), coalesce(platform_arch, ''),
        coalesce(platform_abi, ''), coalesce(platform_python, '')
    );
CREATE TABLE tool_group (
    group_id TEXT NOT NULL PRIMARY KEY,
    summary  TEXT NOT NULL CHECK (length(summary) > 0)
);
CREATE TABLE tool_group_member (
    group_id TEXT NOT NULL,
    tool_id  TEXT NOT NULL REFERENCES tool_asset (tool_id),
    summary  TEXT NOT NULL CHECK (length(summary) > 0),
    PRIMARY KEY (group_id, tool_id),
    FOREIGN KEY (group_id) REFERENCES tool_group (group_id) ON DELETE CASCADE
);
CREATE TABLE tool_group_member_alias (
    group_id TEXT NOT NULL,
    tool_id  TEXT NOT NULL,
    alias    TEXT NOT NULL CHECK (length(alias) > 0),
    PRIMARY KEY (group_id, tool_id, alias),
    FOREIGN KEY (group_id, tool_id)
        REFERENCES tool_group_member (group_id, tool_id) ON DELETE CASCADE
);
CREATE TABLE tool_access (
    access_id TEXT NOT NULL PRIMARY KEY,
    tool_id   TEXT NOT NULL REFERENCES tool_asset (tool_id),
    method    TEXT NOT NULL CHECK (method IN ('dagger', 'uv', 'native', 'api')),
    target    TEXT NOT NULL CHECK (length(target) > 0),
    contract  TEXT NOT NULL CHECK (
        json_valid(contract) AND json_type(contract) = 'object'
    ),
    summary   TEXT NOT NULL CHECK (length(summary) > 0)
);
CREATE TABLE tool_install (
    tool_id         TEXT NOT NULL PRIMARY KEY REFERENCES tool_asset (tool_id),
    command         TEXT NOT NULL CHECK (length(command) > 0),
    version         TEXT NOT NULL CHECK (length(version) > 0),
    entry           TEXT,
    description     TEXT NOT NULL CHECK (length(description) > 0),
    prepared_via    TEXT NOT NULL CHECK (
        prepared_via IN ('uv', 'aria2', 'external')
    ),
    reused          INTEGER NOT NULL CHECK (reused IN (0, 1)),
    source_verified INTEGER NOT NULL CHECK (source_verified IN (0, 1)),
    registered_at   TEXT NOT NULL CHECK (length(registered_at) > 0)
);
CREATE TABLE record_schema (
    schema_version INTEGER PRIMARY KEY CHECK (schema_version = 3)
);
INSERT INTO record_schema (schema_version) VALUES (3);
