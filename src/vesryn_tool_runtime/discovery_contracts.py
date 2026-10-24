"""Discovery query documents over the three records (issue #27, reopened).

The query layer carries the records' own documents — no parallel summary
types, no identity composition, no capability grammar. DiscoveryQuery
filters and pages; DiscoveryPage returns record documents produced by
discovery_records.record_document; diagnostics and query errors stay
separate from ToolResult business status. Querying discovers facts only:
it installs nothing, authorizes nothing and executes nothing.
"""

import re

from .discovery_records import record_from_document
from .documents import ToolRuntimeError
from .schemas import NAME, object_schema, validate

SCHEMA_VERSION = 1

QUERY_KIND = "discovery-query"
PAGE_KIND = "discovery-page"
DIAGNOSTIC_KIND = "discovery-diagnostic"
ERROR_KIND = "discovery-error"

RECORD_KINDS = ("tool-asset", "tool-group", "tool-access")
EFFECTS = ("read", "check", "write")
# Bare tool identities (trivy) and dotted IDs are both valid tool primary
# keys; the old capability-only regex is gone.
TOOL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
DIAGNOSTIC_CODES = (
    "unregistered",
    "undisclosed",
    "scope_excluded",
    "unavailable",
    "unknown",
)
ERROR_CODES = (
    "invalid_query",
    "invalid_document",
    "unknown_reference",
    "conflicting_identity",
    "unsupported_version",
    "unknown_error",
)

DEFAULT_LIMIT = 10
MIN_LIMIT = 1
MAX_LIMIT = 50


class DiscoveryContractError(ToolRuntimeError):
    """A stable query-layer reason code, never a business tool status."""

    def __init__(self, code):
        self.code = code
        super().__init__(f"Discovery contract: {code}")


def _fail(code):
    raise DiscoveryContractError(code)


def _bounded(value, code, *, maximum, allow_empty=False):
    if not isinstance(value, str) or not (allow_empty or value) or len(value) > maximum:
        _fail(code)
    return value


def _enum(value, values, code):
    if value not in values:
        _fail(code)
    return value


def _matches(value, pattern, code):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        _fail(code)
    return value


def _integer(value, code, *, minimum, maximum=None):
    if (
        type(value) is not int
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        _fail(code)
    return value


def _validated(document, schema, kind):
    """Schema-validate strictly, then report gaps by stable code."""
    try:
        validate(document, schema, label="discovery document")
    except ToolRuntimeError:
        _fail("invalid_document")
    return _strip(document, kind)


def _strip(document, kind):
    if not isinstance(document, dict):
        _fail("invalid_document")
    value = dict(document)
    if (
        type(value.get("schema_version")) is not int
        or value["schema_version"] != SCHEMA_VERSION
        or value.get("kind") != kind
    ):
        _fail("invalid_document")
    del value["schema_version"], value["kind"]
    return value


QUERY_SCHEMA = {
    **object_schema(
        {
            "schema_version": {"const": SCHEMA_VERSION, "type": "integer"},
            "kind": {"const": QUERY_KIND},
            "query": {"type": "string", "maxLength": 256},
            "operation": {"type": "string", "minLength": 1, "maxLength": 256},
            "domain": {"type": "string", "pattern": NAME["pattern"]},
            "environment": {"type": "string", "pattern": NAME["pattern"]},
            "effect": {"enum": list(EFFECTS)},
            "group_id": {"type": "string", "pattern": TOOL_ID.pattern},
            "catalog_ref": {"type": "string", "pattern": NAME["pattern"]},
            "offset": {"type": "integer", "minimum": 0},
            "limit": {
                "type": "integer",
                "minimum": MIN_LIMIT,
                "maximum": MAX_LIMIT,
            },
            "discovery_id": {
                "type": "string",
                "minLength": 1,
                "maxLength": 256,
            },
        },
        ["schema_version", "kind", "offset", "limit"],
    ),
}

DIAGNOSTIC_SCHEMA = {
    **object_schema(
        {
            "schema_version": {"const": SCHEMA_VERSION, "type": "integer"},
            "kind": {"const": DIAGNOSTIC_KIND},
            "code": {"enum": list(DIAGNOSTIC_CODES)},
            "detail": {"type": "string", "maxLength": 512},
            "ref": {"type": "string", "minLength": 1, "maxLength": 256},
        },
        ["schema_version", "kind", "code"],
    ),
}

ERROR_SCHEMA = {
    **object_schema(
        {
            "schema_version": {"const": SCHEMA_VERSION, "type": "integer"},
            "kind": {"const": ERROR_KIND},
            "code": {"enum": list(ERROR_CODES)},
            "detail": {"type": "string", "maxLength": 512},
        },
        ["schema_version", "kind", "code"],
    ),
}

PAGE_SCHEMA = {
    **object_schema(
        {
            "schema_version": {"const": SCHEMA_VERSION, "type": "integer"},
            "kind": {"const": PAGE_KIND},
            "record_kind": {"enum": list(RECORD_KINDS)},
            "offset": {"type": "integer", "minimum": 0},
            "limit": {
                "type": "integer",
                "minimum": MIN_LIMIT,
                "maximum": MAX_LIMIT,
            },
            "next_offset": {"type": "integer", "minimum": 0},
            "total": {"type": "integer", "minimum": 0},
            "query": {"type": "object"},
            "records": {"type": "array", "items": {"type": "object"}},
            "diagnostics": {"type": "array", "items": {"type": "object"}},
        },
        [
            "schema_version",
            "kind",
            "record_kind",
            "offset",
            "limit",
            "total",
            "query",
            "records",
        ],
    ),
}


class DiscoveryQuery:
    """Caller-side filter facts; no filter confers any permission."""

    __slots__ = (
        "catalog_ref",
        "discovery_id",
        "domain",
        "effect",
        "environment",
        "group_id",
        "limit",
        "offset",
        "operation",
        "query",
    )

    def __init__(
        self,
        query="",
        operation=None,
        domain=None,
        environment=None,
        effect=None,
        group_id=None,
        catalog_ref=None,
        offset=0,
        limit=DEFAULT_LIMIT,
        discovery_id=None,
    ):
        code = "invalid_query"
        _bounded(query, code, maximum=256, allow_empty=True)
        for value in (operation, discovery_id):
            if value is not None:
                _bounded(value, code, maximum=256)
        for value in (domain, environment, catalog_ref):
            if value is not None:
                _matches(value, re.compile(NAME["pattern"]), code)
        if effect is not None:
            _enum(effect, EFFECTS, code)
        if group_id is not None:
            _matches(group_id, TOOL_ID, code)
        _integer(offset, code, minimum=0)
        _integer(limit, code, minimum=MIN_LIMIT, maximum=MAX_LIMIT)
        self.query = query
        self.operation = operation
        self.domain = domain
        self.environment = environment
        self.effect = effect
        self.group_id = group_id
        self.catalog_ref = catalog_ref
        self.offset = offset
        self.limit = limit
        self.discovery_id = discovery_id

    def document(self):
        value = {"schema_version": SCHEMA_VERSION, "kind": QUERY_KIND}
        for name in (
            "query",
            "operation",
            "domain",
            "environment",
            "effect",
            "group_id",
            "catalog_ref",
            "discovery_id",
        ):
            item = getattr(self, name)
            if item:
                value[name] = item
        value.update({"offset": self.offset, "limit": self.limit})
        return value

    @classmethod
    def from_document(cls, document):
        document = _validated(document, QUERY_SCHEMA, QUERY_KIND)
        try:
            return cls(**document)
        except TypeError:
            _fail("invalid_document")


class DiscoveryDiagnostic:
    """A structured query-layer fact; never a ToolResult business status."""

    __slots__ = ("code", "detail", "ref")

    def __init__(self, code, detail="", ref=None):
        _enum(code, DIAGNOSTIC_CODES, "invalid_document")
        _bounded(detail, "invalid_document", maximum=512, allow_empty=True)
        if ref is not None:
            _bounded(ref, "invalid_document", maximum=256)
        self.code = code
        self.detail = detail
        self.ref = ref

    def document(self):
        value = {
            "schema_version": SCHEMA_VERSION,
            "kind": DIAGNOSTIC_KIND,
            "code": self.code,
        }
        if self.detail:
            value["detail"] = self.detail
        if self.ref is not None:
            value["ref"] = self.ref
        return value

    @classmethod
    def from_document(cls, document):
        document = _validated(document, DIAGNOSTIC_SCHEMA, DIAGNOSTIC_KIND)
        try:
            return cls(**document)
        except TypeError:
            _fail("invalid_document")


class DiscoveryErrorDocument:
    """A query-layer error shape, apart from ToolResult business status."""

    __slots__ = ("code", "detail")

    def __init__(self, code, detail=""):
        _enum(code, ERROR_CODES, "invalid_document")
        _bounded(detail, "invalid_document", maximum=512, allow_empty=True)
        self.code = code
        self.detail = detail

    def document(self):
        value = {
            "schema_version": SCHEMA_VERSION,
            "kind": ERROR_KIND,
            "code": self.code,
        }
        if self.detail:
            value["detail"] = self.detail
        return value

    @classmethod
    def from_document(cls, document):
        document = _validated(document, ERROR_SCHEMA, ERROR_KIND)
        try:
            return cls(**document)
        except TypeError:
            _fail("invalid_document")


def _as_record_document(record):
    """Accept a record object or its document; the record layer validates."""
    if isinstance(record, dict):
        record_from_document(record)
        return record
    from .discovery_records import record_document

    return record_document(record)


class DiscoveryPage:
    """A result page of record documents with deterministic paging facts.

    ``total`` counts disclosable records only; ``next_offset`` is omitted
    when no next page exists. Records are homogeneous documents validated
    through the record layer — this class invents no fields of its own.
    """

    __slots__ = (
        "diagnostics",
        "limit",
        "next_offset",
        "offset",
        "query",
        "record_kind",
        "records",
        "total",
    )

    def __init__(
        self,
        record_kind,
        offset,
        limit,
        total,
        query,
        records,
        diagnostics=(),
        next_offset=None,
    ):
        code = "invalid_document"
        _enum(record_kind, RECORD_KINDS, code)
        _integer(offset, code, minimum=0)
        _integer(limit, code, minimum=MIN_LIMIT, maximum=MAX_LIMIT)
        _integer(total, code, minimum=0)
        if not isinstance(query, DiscoveryQuery):
            _fail(code)
        if not isinstance(records, tuple):
            _fail(code)
        expected = min(max(total - offset, 0), limit)
        if len(records) != expected:
            _fail(code)
        if next_offset is not None:
            _integer(next_offset, code, minimum=0)
        if total > offset + len(records):
            if next_offset != offset + len(records):
                _fail(code)
        elif next_offset is not None:
            _fail(code)
        self.records = tuple(_as_record_document(record) for record in records)
        if not isinstance(diagnostics, tuple) or any(
            not isinstance(item, DiscoveryDiagnostic) for item in diagnostics
        ):
            _fail(code)
        self.record_kind = record_kind
        self.offset = offset
        self.limit = limit
        self.total = total
        self.query = query
        self.diagnostics = diagnostics
        self.next_offset = next_offset

    def document(self):
        value = {
            "schema_version": SCHEMA_VERSION,
            "kind": PAGE_KIND,
            "record_kind": self.record_kind,
            "offset": self.offset,
            "limit": self.limit,
            "total": self.total,
            "query": self.query.document(),
            "records": [dict(record) for record in self.records],
        }
        if self.next_offset is not None:
            value["next_offset"] = self.next_offset
        if self.diagnostics:
            value["diagnostics"] = [item.document() for item in self.diagnostics]
        return value

    @classmethod
    def from_document(cls, document):
        document = _validated(document, PAGE_SCHEMA, PAGE_KIND)
        try:
            document["query"] = DiscoveryQuery.from_document(document["query"])
            document["records"] = tuple(
                _as_record_document(record) for record in document["records"]
            )
            document["diagnostics"] = tuple(
                DiscoveryDiagnostic.from_document(item)
                for item in document.pop("diagnostics", ())
            )
            return cls(**document)
        except TypeError, KeyError:
            _fail("invalid_document")
