"""Live-declaration loading and explicit composition over the three records.

The bundled seed (``record_seed.sql``, shipped as a package resource) is the
single live declaration source; ``bundled_records()`` reads it into records
without touching any persistent database. ``compose_catalog`` combines
explicitly chosen sources — record iterables and/or opened stores — into one
read-only view: identical records collapse to a single entry, the same
primary key with different content is an explicit conflict, and nothing is
auto-scanned or auto-registered. Composing, importing or missing reads never
create, migrate or write persistent state; registration happens only through
``RecordStore.put_records`` / the per-record gateways at a caller-chosen
path. Registration facts grant no permission and imply nothing about
installation, binding or execution.
"""

from .discovery_records import (
    RecordError,
    ToolAccess,
    ToolAsset,
    ToolGroup,
)
from .record_schema import seed_sql
from .record_store import RecordStore, open_record_store


def bundled_records():
    """The live declaration from the bundled seed, as records.

    Parsing goes through an in-memory database so the declared SQL is read
    exactly as the frozen schema defines it; no persistent store is created
    or opened. Order is stable: assets, groups, accesses, each by primary
    key — ready for ``RecordStore.put_records`` at a caller-chosen path.
    """
    store = open_record_store(":memory:")
    try:
        store._db.executescript(seed_sql())
        records = [
            *store.assets.all(),
            *store.groups.all(),
            *store.accesses.all(),
        ]
    finally:
        store.close()
    return tuple(records)


class ComposedCatalog:
    """An in-memory read view over explicitly composed record sources."""

    def __init__(self, records):
        assets, groups, accesses = {}, {}, {}
        for record in records:
            if isinstance(record, ToolAsset):
                _merge(assets, record.tool_id, record, "duplicate_tool_id")
            elif isinstance(record, ToolGroup):
                _merge(groups, record.group_id, record, "duplicate_group_id")
            elif isinstance(record, ToolAccess):
                _merge(accesses, record.access_id, record, "duplicate_access_id")
            else:
                raise RecordError("invalid_record")
        self._assets = assets
        self._groups = groups
        self._accesses = accesses
        # References are validated once, over the MERGED catalog: cross-source
        # references are fine, but a member or entry whose tool is missing
        # from every source is an explicit refusal — never a dangling record
        # downstream consumers cannot resolve.
        for group in groups.values():
            for member in group.members:
                if member.tool_id not in assets:
                    raise RecordError("unknown_tool")
        for access in accesses.values():
            if access.tool_id not in assets:
                raise RecordError("unknown_tool")

    def asset(self, tool_id):
        try:
            return self._assets[tool_id]
        except KeyError:
            raise RecordError("unknown_tool") from None

    def group(self, group_id):
        try:
            return self._groups[group_id]
        except KeyError:
            raise RecordError("unknown_group") from None

    def access(self, access_id):
        try:
            return self._accesses[access_id]
        except KeyError:
            raise RecordError("unknown_access") from None

    def accesses_for(self, tool_id):
        """Every entry of one tool; () when the tool has no entry yet.

        An unregistered tool is ``unknown_tool`` — distinct from a
        registered tool without entries, and never an execution failure.
        """
        self.asset(tool_id)
        return tuple(
            self._accesses[access_id]
            for access_id in sorted(self._accesses)
            if self._accesses[access_id].tool_id == tool_id
        )

    def tools(self):
        """All tools, ordered by tool primary key (base traversal)."""
        return tuple(self._assets[key] for key in sorted(self._assets))

    def groups(self):
        """All groups, ordered by group primary key (base traversal)."""
        return tuple(self._groups[key] for key in sorted(self._groups))

    def accesses(self):
        """All entries, ordered by access primary key (base traversal)."""
        return tuple(self._accesses[key] for key in sorted(self._accesses))


def _merge(mapping, key, record, duplicate_code):
    existing = mapping.get(key)
    if existing is not None and existing != record:
        raise RecordError(duplicate_code)
    mapping[key] = record


def compose_catalog(*sources):
    """Combine explicitly chosen sources into one read-only catalog view.

    Each source is an iterable of records or an opened ``RecordStore`` (its
    current contents are read); sources are combined only because the caller
    named them. Identical records collapse to one entry; the same primary
    key with different content raises — load order never silently wins.
    """
    records = []
    for source in sources:
        if source is None:
            continue
        if isinstance(source, RecordStore):
            records.extend(source.assets.all())
            records.extend(source.groups.all())
            records.extend(source.accesses.all())
        else:
            records.extend(source)
    return ComposedCatalog(records)


# -- temporary bridge for the old preparation callers (#33 removes it) -------
#
# The uv/aria2 preparation backends still consume the legacy AssetDefinition
# selection model. This derived view maps the live records onto that shape so
# the old callers read the SAME declaration source; it writes nothing, is not
# a second authority, and is deleted by #33 together with its callers
# (examples/native_asset_delivery.py, examples/asset_acceptance.py and the
# uv/aria2 selection path).

_LEGACY_BACKEND = {
    "uv": ("python", "uv"),
    "github-release": ("native", "aria2"),
    "oci": ("oci", "oci"),
}


def legacy_preparation_definitions():
    """Read-only AssetDefinition view over the bundled live records.

    Temporary: exists only while #33 migrates the preparation backends to
    consume records directly. One AssetDefinition per tool; releases map
    provider→distribution/backend, digest→sha256, version python→
    requires_python and the tool entrypoint is used per release (the native
    backend's existing entrypoint/.exe variant matching covers Windows).
    """
    from .assets import AssetDefinition, AssetRelease

    definitions = []
    store = open_record_store(":memory:")
    try:
        store._db.executescript(seed_sql())
        assets = store.assets.all()
    finally:
        store.close()
    for asset in assets:
        releases = []
        for item in asset.versions:
            distribution, backend = _LEGACY_BACKEND[asset.provider]
            releases.append(
                AssetRelease(
                    item.version,
                    distribution,
                    backend,
                    item.source,
                    item.digest,
                    asset.entrypoint,
                    os=item.platform.os if item.platform else "any",
                    arch=item.platform.arch if item.platform else "any",
                    abi=item.platform.abi if item.platform else None,
                    requires_python=item.python if distribution == "python" else None,
                    package=asset.package if distribution == "python" else None,
                )
            )
        definitions.append(
            AssetDefinition(
                asset.tool_id,
                "live-records-view",
                tuple(releases),
            )
        )
    return tuple(definitions)
