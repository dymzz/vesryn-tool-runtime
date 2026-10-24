CREATE TABLE tool_asset (
    tool_id    TEXT PRIMARY KEY,
    name       TEXT NOT NULL CHECK (length(name) > 0),
    provider   TEXT NOT NULL CHECK (provider IN ('uv', 'github-release', 'oci')),
    package    TEXT,
    entrypoint TEXT NOT NULL CHECK (length(entrypoint) > 0)
);
CREATE TABLE tool_release (
    tool_id       TEXT NOT NULL REFERENCES tool_asset (tool_id),
    version       TEXT NOT NULL CHECK (length(version) > 0),
    platform_os   TEXT,
    platform_arch TEXT,
    source        TEXT NOT NULL CHECK (length(source) > 0),
    digest_type   TEXT NOT NULL CHECK (digest_type IN ('sha256')),
    digest        TEXT NOT NULL CHECK (length(digest) > 0),
    CHECK ((platform_os IS NULL) = (platform_arch IS NULL)),
    CHECK (
        platform_os IS NULL
        OR (length(platform_os) > 0 AND length(platform_arch) > 0)
    ),
    CHECK (digest_type != 'sha256' OR length(digest) = 64)
);
CREATE UNIQUE INDEX tool_release_identity
    ON tool_release (
        tool_id, version, coalesce(platform_os, ''), coalesce(platform_arch, '')
    );
CREATE TABLE tool_group (
    group_id TEXT PRIMARY KEY,
    summary  TEXT NOT NULL CHECK (length(summary) > 0)
);
CREATE TABLE tool_group_member (
    group_id TEXT NOT NULL REFERENCES tool_group (group_id) ON DELETE CASCADE,
    tool_id  TEXT NOT NULL REFERENCES tool_asset (tool_id),
    summary  TEXT NOT NULL CHECK (length(summary) > 0),
    PRIMARY KEY (group_id, tool_id)
);
CREATE TABLE tool_group_member_alias (
    group_id TEXT NOT NULL REFERENCES tool_group (group_id) ON DELETE CASCADE,
    tool_id  TEXT NOT NULL REFERENCES tool_asset (tool_id),
    alias    TEXT NOT NULL CHECK (length(alias) > 0),
    PRIMARY KEY (group_id, tool_id, alias)
);
CREATE TABLE tool_access (
    access_id TEXT PRIMARY KEY,
    tool_id   TEXT NOT NULL REFERENCES tool_asset (tool_id),
    method    TEXT NOT NULL CHECK (method IN ('dagger', 'uv', 'native', 'api')),
    target    TEXT NOT NULL CHECK (length(target) > 0),
    contract  TEXT NOT NULL CHECK (
        json_valid(contract) AND json_type(contract) = 'object'
    ),
    summary   TEXT NOT NULL CHECK (length(summary) > 0)
);
CREATE TABLE record_schema (
    schema_version INTEGER PRIMARY KEY CHECK (schema_version = 1)
);
INSERT INTO record_schema (schema_version) VALUES (1);
