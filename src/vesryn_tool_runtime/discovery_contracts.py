"""Discovery field contracts: documents, schemas, serialization and thin validation.

This module is the single field authority for progressive discovery and access
entry queries (issue #14). It defines every public document, its exact keys,
value domains, fact-state enums, identity composition and omission rules. It
implements no retrieval, ranking, admission, binding or health algorithms: a
field can represent a fact without that fact being verified, and constructing
any document here grants no permission and reports no readiness.
"""

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from dataclasses import fields as dataclass_fields

from .contracts import ToolSpec
from .documents import ToolRuntimeError
from .schemas import CONTRACT_VERSION, DRAFT, NAME, TOOL, object_schema, validate

SCHEMA_VERSION = 1

QUERY_KIND = "discovery-query"
PAGE_KIND = "discovery-page"
GROUP_KIND = "group-summary"
CANDIDATE_KIND = "candidate-summary"
ACCESS_KIND = "access-entry-summary"
CONTRACT_KIND = "contract-detail"
DIAGNOSTIC_KIND = "discovery-diagnostic"
ERROR_KIND = "discovery-error"

EFFECTS = ("read", "check", "write")
ITEM_KINDS = (CANDIDATE_KIND, GROUP_KIND, ACCESS_KIND)
ASSEMBLY_STATES = ("assembled", "missing", "unknown")
BINDING_STATES = (
    "not_provided",
    "known_absent",
    "pending_validation",
    "valid",
    "invalid",
    "not_required",
)
SCOPE_STATES = ("matched", "excluded")
ADMISSION_STATES = ("not_evaluated", "admitted", "rejected")
AVAILABILITY_STATES = ("unknown", "available", "unavailable")
DIAGNOSTIC_CODES = (
    "unregistered",
    "undisclosed",
    "scope_excluded",
    "unassembled",
    "binding_invalid",
    "binding_unverified",
    "unavailable",
    "unknown_input",
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

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
_NAME = re.compile(NAME["pattern"])
_TOOL = re.compile(TOOL["pattern"])
_HASH = re.compile(r"[0-9a-f]{64}")
_VERSION = re.compile(CONTRACT_VERSION["pattern"])
_WITH_BINDING = frozenset({"pending_validation", "valid", "invalid"})
_CONTRACT_REQUIRED = frozenset(
    {
        "tool_id",
        "input_schema",
        "output_schema",
        "contract_version",
        "effect",
        "recovery",
        "reuse",
        "environments",
    }
)
_CONTRACT_ALLOWED = (
    frozenset(_CONTRACT_REQUIRED)
    | {item.name for item in dataclass_fields(ToolSpec)}
    | {"contract_sha256"}
)


class DiscoveryContractError(ToolRuntimeError):
    """A stable field-contract reason code, never a business tool status."""

    def __init__(self, code):
        self.code = code
        super().__init__(f"Discovery contract: {code}")


def _fail(code):
    raise DiscoveryContractError(code)


def _bounded(value, code, *, maximum, allow_empty=False):
    if (
        not isinstance(value, str)
        or not (allow_empty or value)
        or len(value) > (maximum)
    ):
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


def compose_access_id(catalog_ref, tool_id, entry_key):
    """The stable logical entry identity: ``<catalog_ref>:<tool_id>@<entry_key>``.

    Composed only from host-provided stable names — never from binding
    parameters, query-generated IDs, object addresses or install locations —
    and version/contract-digest changes never enter it.
    """
    _matches(catalog_ref, _NAME, "invalid_query")
    _matches(tool_id, _TOOL, "invalid_query")
    _matches(entry_key, _NAME, "invalid_query")
    return f"{catalog_ref}:{tool_id}@{entry_key}"


def _entry_identity(entry, code):
    """Validate the entry's naming parts and its composed access identity."""
    _matches(entry.catalog_ref, _NAME, code)
    _matches(entry.tool_id, _TOOL, code)
    _matches(entry.entry_key, _NAME, code)
    if entry.access_id is None:
        object.__setattr__(
            entry,
            "access_id",
            f"{entry.catalog_ref}:{entry.tool_id}@{entry.entry_key}",
        )
    if entry.access_id != (f"{entry.catalog_ref}:{entry.tool_id}@{entry.entry_key}"):
        _fail(code)


def _source(value, code):
    if not isinstance(value, Mapping):
        _fail(code)
    value = dict(value)
    if set(value) != {"kind", "identity", "interface_sha256"}:
        _fail(code)
    _matches(value["kind"], _NAME, code)
    _bounded(value["identity"], code, maximum=1024)
    _matches(value["interface_sha256"], _HASH, code)
    return value


def _strip(document, kind):
    """Verify the envelope and drop it, keeping strict-key construction next."""
    if not isinstance(document, Mapping):
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


def _validated(document, schema, kind):
    """Schema-validate strictly, then report every parse gap by stable code."""
    try:
        validate(document, schema, label="discovery document")
    except ToolRuntimeError:
        _fail("invalid_document")
    return _strip(document, kind)


def _string_schema(maximum, minimum=0):
    return {"type": "string", "minLength": minimum, "maxLength": maximum}


def _enum_schema(values):
    return {"enum": list(values)}


QUERY_SCHEMA = {
    "$schema": DRAFT,
    **object_schema(
        {
            "schema_version": {"const": SCHEMA_VERSION, "type": "integer"},
            "kind": {"const": QUERY_KIND},
            "query": _string_schema(256),
            "operation": _string_schema(256, minimum=1),
            "domain": {"type": "string", "pattern": NAME["pattern"]},
            "environment": {"type": "string", "pattern": NAME["pattern"]},
            "effect": _enum_schema(EFFECTS),
            "group_id": {"type": "string", "pattern": TOOL["pattern"]},
            "catalog_ref": {"type": "string", "pattern": NAME["pattern"]},
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": MIN_LIMIT, "maximum": MAX_LIMIT},
            "discovery_id": _string_schema(256, minimum=1),
        },
        ["schema_version", "kind", "offset", "limit"],
    ),
}

DIAGNOSTIC_SCHEMA = {
    "$schema": DRAFT,
    **object_schema(
        {
            "schema_version": {"const": SCHEMA_VERSION, "type": "integer"},
            "kind": {"const": DIAGNOSTIC_KIND},
            "code": _enum_schema(DIAGNOSTIC_CODES),
            "detail": _string_schema(512),
            "ref": _string_schema(256, minimum=1),
        },
        ["schema_version", "kind", "code"],
    ),
}

GROUP_SCHEMA = {
    "$schema": DRAFT,
    **object_schema(
        {
            "schema_version": {"const": SCHEMA_VERSION, "type": "integer"},
            "kind": {"const": GROUP_KIND},
            "group_id": {"type": "string", "pattern": TOOL["pattern"]},
            "catalog_ref": {"type": "string", "pattern": NAME["pattern"]},
            "display_name": _string_schema(120),
            "description": _string_schema(4096),
            "aliases": {
                "type": "array",
                "maxItems": 64,
                "uniqueItems": True,
                "items": _string_schema(128, minimum=1),
            },
            "members": {
                "type": "array",
                "minItems": 1,
                "items": object_schema(
                    {
                        "tool_id": {"type": "string", "pattern": TOOL["pattern"]},
                        "catalog_ref": {
                            "type": "string",
                            "pattern": NAME["pattern"],
                        },
                    }
                ),
            },
            "member_count": {"type": "integer", "minimum": 1},
        },
        [
            "schema_version",
            "kind",
            "group_id",
            "catalog_ref",
            "members",
            "member_count",
        ],
    ),
}

CANDIDATE_SCHEMA = {
    "$schema": DRAFT,
    **object_schema(
        {
            "schema_version": {"const": SCHEMA_VERSION, "type": "integer"},
            "kind": {"const": CANDIDATE_KIND},
            "tool_id": {"type": "string", "pattern": TOOL["pattern"]},
            "display_name": _string_schema(120),
            "description": _string_schema(240),
            "domain": {"type": "string", "pattern": NAME["pattern"]},
            "effect": _enum_schema(EFFECTS),
            "contract_version": {
                "type": "string",
                "pattern": CONTRACT_VERSION["pattern"],
            },
            "contract_sha256": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
            "provider": {"type": "string", "pattern": NAME["pattern"]},
            "catalog_ref": {"type": "string", "pattern": NAME["pattern"]},
            "environments": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "string", "pattern": NAME["pattern"]},
            },
            "group_id": {"type": "string", "pattern": TOOL["pattern"]},
            "matched_alias": _string_schema(128, minimum=1),
            "asset_id": {
                "type": "string",
                "pattern": _TOKEN.pattern,
            },
        },
        [
            "schema_version",
            "kind",
            "tool_id",
            "description",
            "domain",
            "effect",
            "contract_version",
            "contract_sha256",
            "provider",
            "catalog_ref",
            "environments",
        ],
    ),
}

ACCESS_SCHEMA = {
    "$schema": DRAFT,
    **object_schema(
        {
            "schema_version": {"const": SCHEMA_VERSION, "type": "integer"},
            "kind": {"const": ACCESS_KIND},
            "access_id": _string_schema(256, minimum=1),
            "catalog_ref": {"type": "string", "pattern": NAME["pattern"]},
            "tool_id": {"type": "string", "pattern": TOOL["pattern"]},
            "entry_key": {"type": "string", "pattern": NAME["pattern"]},
            "provider": {"type": "string", "pattern": NAME["pattern"]},
            "environment": {"type": "string", "pattern": NAME["pattern"]},
            "purpose": _string_schema(1024, minimum=1),
            "contract_version": {
                "type": "string",
                "pattern": CONTRACT_VERSION["pattern"],
            },
            "contract_sha256": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
            "source": object_schema(
                {
                    "kind": {"type": "string", "pattern": NAME["pattern"]},
                    "identity": _string_schema(1024, minimum=1),
                    "interface_sha256": {
                        "type": "string",
                        "pattern": r"^[0-9a-f]{64}$",
                    },
                }
            ),
            "discovery_scope": _enum_schema(SCOPE_STATES),
            "assembly": _enum_schema(ASSEMBLY_STATES),
            "binding": _enum_schema(BINDING_STATES),
            "binding_id": _string_schema(128, minimum=1),
            "execution_admission": _enum_schema(ADMISSION_STATES),
            "availability": _enum_schema(AVAILABILITY_STATES),
            "reason_code": _enum_schema(DIAGNOSTIC_CODES),
        },
        [
            "schema_version",
            "kind",
            "access_id",
            "catalog_ref",
            "tool_id",
            "entry_key",
            "provider",
            "environment",
            "purpose",
            "contract_version",
            "contract_sha256",
            "discovery_scope",
        ],
    ),
}

PAGE_SCHEMA = {
    "$schema": DRAFT,
    **object_schema(
        {
            "schema_version": {"const": SCHEMA_VERSION, "type": "integer"},
            "kind": {"const": PAGE_KIND},
            "item_kind": _enum_schema(ITEM_KINDS),
            "disclosure": {"const": "summary"},
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": MIN_LIMIT, "maximum": MAX_LIMIT},
            "next_offset": {"type": "integer", "minimum": 0},
            "total": {"type": "integer", "minimum": 0},
            "query": {"type": "object"},
            "items": {"type": "array", "items": {"type": "object"}},
            "diagnostics": {"type": "array", "items": {"type": "object"}},
        },
        [
            "schema_version",
            "kind",
            "item_kind",
            "disclosure",
            "offset",
            "limit",
            "total",
            "query",
            "items",
        ],
    ),
}

ERROR_SCHEMA = {
    "$schema": DRAFT,
    **object_schema(
        {
            "schema_version": {"const": SCHEMA_VERSION, "type": "integer"},
            "kind": {"const": ERROR_KIND},
            "code": _enum_schema(ERROR_CODES),
            "detail": _string_schema(512),
        },
        ["schema_version", "kind", "code"],
    ),
}


@dataclass(frozen=True)
class DiscoveryQuery:
    """Caller-side filter facts; no filter confers any permission."""

    query: str = ""
    operation: str | None = None
    domain: str | None = None
    environment: str | None = None
    effect: str | None = None
    group_id: str | None = None
    catalog_ref: str | None = None
    offset: int = 0
    limit: int = DEFAULT_LIMIT
    discovery_id: str | None = None

    def __post_init__(self):
        code = "invalid_query"
        _bounded(self.query, code, maximum=256, allow_empty=True)
        for value in (self.operation, self.discovery_id):
            if value is not None:
                _bounded(value, code, maximum=256)
        if self.domain is not None:
            _matches(self.domain, _NAME, code)
        if self.environment is not None:
            _matches(self.environment, _NAME, code)
        if self.effect is not None:
            _enum(self.effect, EFFECTS, code)
        if self.group_id is not None:
            _matches(self.group_id, _TOOL, code)
        if self.catalog_ref is not None:
            _matches(self.catalog_ref, _NAME, code)
        _integer(self.offset, code, minimum=0)
        _integer(self.limit, code, minimum=MIN_LIMIT, maximum=MAX_LIMIT)

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


@dataclass(frozen=True)
class DiscoveryDiagnostic:
    """A structured query-layer fact; never a ToolResult business status.

    ``detail`` and ``ref`` must not disclose hidden items: no identifiers,
    reasons, totals or member lists of anything absent from the same result.
    """

    code: str
    detail: str = ""
    ref: str | None = None

    def __post_init__(self):
        code = "invalid_document"
        _enum(self.code, DIAGNOSTIC_CODES, code)
        _bounded(self.detail, code, maximum=512, allow_empty=True)
        if self.ref is not None:
            _bounded(self.ref, code, maximum=256)

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


@dataclass(frozen=True)
class GroupMember:
    """A reference to an existing capability; it copies no contract or Adapter."""

    tool_id: str
    catalog_ref: str

    def __post_init__(self):
        _matches(self.tool_id, _TOOL, "invalid_document")
        _matches(self.catalog_ref, _NAME, "invalid_document")

    def document(self):
        return asdict(self)

    @classmethod
    def from_document(cls, document):
        try:
            return cls(**dict(document))
        except TypeError:
            _fail("invalid_document")


@dataclass(frozen=True)
class GroupSummary:
    """A disclosure-bounded group summary; aliases create no capability identity."""

    group_id: str
    catalog_ref: str
    members: tuple[GroupMember, ...]
    member_count: int
    display_name: str = ""
    description: str = ""
    aliases: tuple[str, ...] = ()

    def __post_init__(self):
        code = "invalid_document"
        _matches(self.group_id, _TOOL, code)
        _matches(self.catalog_ref, _NAME, code)
        _bounded(self.display_name, code, maximum=120, allow_empty=True)
        _bounded(self.description, code, maximum=4096, allow_empty=True)
        for alias in self.aliases:
            _bounded(alias, code, maximum=128)
        if len(set(self.aliases)) != len(self.aliases):
            _fail(code)
        if (
            not isinstance(self.members, tuple)
            or not self.members
            or any(not isinstance(item, GroupMember) for item in self.members)
        ):
            _fail(code)
        references = [(item.catalog_ref, item.tool_id) for item in self.members]
        if len(set(references)) != len(references):
            _fail("conflicting_identity")
        # Only disclosable members appear here, so the count equals the list.
        if self.member_count != len(self.members):
            _fail(code)

    def document(self):
        value = {
            "schema_version": SCHEMA_VERSION,
            "kind": GROUP_KIND,
            "group_id": self.group_id,
            "catalog_ref": self.catalog_ref,
            "member_count": self.member_count,
            "members": [item.document() for item in self.members],
        }
        if self.display_name:
            value["display_name"] = self.display_name
        if self.description:
            value["description"] = self.description
        if self.aliases:
            value["aliases"] = list(self.aliases)
        return value

    @classmethod
    def from_document(cls, document):
        document = dict(_validated(document, GROUP_SCHEMA, GROUP_KIND))
        try:
            document["members"] = tuple(
                GroupMember.from_document(item) for item in document["members"]
            )
            document["aliases"] = tuple(document.pop("aliases", ()))
            return cls(**document)
        except TypeError, KeyError:
            _fail("invalid_document")


@dataclass(frozen=True)
class CandidateSummary:
    """A ToolSpec.summary()-derived candidate; it never carries Schemas."""

    tool_id: str
    description: str
    domain: str
    effect: str
    contract_version: str
    contract_sha256: str
    provider: str
    catalog_ref: str
    environments: tuple[str, ...]
    display_name: str = ""
    group_id: str | None = None
    matched_alias: str | None = None
    asset_id: str | None = None

    def __post_init__(self):
        code = "invalid_document"
        _matches(self.tool_id, _TOOL, code)
        _bounded(self.description, code, maximum=240, allow_empty=True)
        _matches(self.domain, _NAME, code)
        _enum(self.effect, EFFECTS, code)
        _matches(self.contract_version, _VERSION, code)
        _matches(self.contract_sha256, _HASH, code)
        _matches(self.provider, _NAME, code)
        _matches(self.catalog_ref, _NAME, code)
        if (
            not isinstance(self.environments, tuple)
            or not self.environments
            or any(not isinstance(item, str) for item in self.environments)
        ):
            _fail(code)
        for item in self.environments:
            _matches(item, _NAME, code)
        _bounded(self.display_name, code, maximum=120, allow_empty=True)
        if self.group_id is not None:
            _matches(self.group_id, _TOOL, code)
        if self.matched_alias is not None:
            _bounded(self.matched_alias, code, maximum=128)
        if self.asset_id is not None:
            _matches(self.asset_id, _TOKEN, code)

    @classmethod
    def from_spec(
        cls,
        spec,
        *,
        provider,
        catalog_ref,
        environments=None,
        group_id=None,
        matched_alias=None,
        asset_id=None,
    ):
        """Derive the summary from the existing ToolSpec summary, field by field."""
        if not isinstance(spec, ToolSpec):
            _fail("invalid_document")
        summary = spec.summary()
        applicable = spec.environments if environments is None else environments
        return cls(
            tool_id=summary["tool_id"],
            display_name=summary.get("display_name", ""),
            description=summary["description"],
            domain=summary["domain"],
            effect=summary["effect"],
            contract_version=summary["contract_version"],
            contract_sha256=summary["contract_sha256"],
            provider=provider,
            catalog_ref=catalog_ref,
            environments=tuple(applicable),
            group_id=group_id,
            matched_alias=matched_alias,
            asset_id=asset_id,
        )

    def document(self):
        value = {
            "schema_version": SCHEMA_VERSION,
            "kind": CANDIDATE_KIND,
            "tool_id": self.tool_id,
            "description": self.description,
            "domain": self.domain,
            "effect": self.effect,
            "contract_version": self.contract_version,
            "contract_sha256": self.contract_sha256,
            "provider": self.provider,
            "catalog_ref": self.catalog_ref,
            "environments": list(self.environments),
        }
        if self.display_name:
            value["display_name"] = self.display_name
        if self.group_id is not None:
            value["group_id"] = self.group_id
        if self.matched_alias is not None:
            value["matched_alias"] = self.matched_alias
        if self.asset_id is not None:
            value["asset_id"] = self.asset_id
        return value

    @classmethod
    def from_document(cls, document):
        document = dict(_validated(document, CANDIDATE_SCHEMA, CANDIDATE_KIND))
        try:
            document["environments"] = tuple(document["environments"])
            return cls(**document)
        except TypeError, KeyError:
            _fail("invalid_document")


@dataclass(frozen=True)
class AccessEntrySummary:
    """One logical access entry with separated, sourced facts — never "ready".

    Every fact state is an explicit enum value; unknown never means allowed,
    installed or healthy, and no default states a positive fact.
    """

    tool_id: str
    catalog_ref: str
    entry_key: str
    provider: str
    environment: str
    purpose: str
    contract_version: str
    contract_sha256: str
    discovery_scope: str
    access_id: str | None = None
    source: Mapping | None = None
    assembly: str = "unknown"
    binding: str = "not_provided"
    binding_id: str | None = None
    execution_admission: str = "not_evaluated"
    availability: str = "unknown"
    reason_code: str | None = None

    def __post_init__(self):
        code = "invalid_document"
        _entry_identity(self, code)
        _matches(self.provider, _NAME, code)
        _matches(self.environment, _NAME, code)
        _bounded(self.purpose, code, maximum=1024)
        _matches(self.contract_version, _VERSION, code)
        _matches(self.contract_sha256, _HASH, code)
        _enum(self.discovery_scope, SCOPE_STATES, code)
        _enum(self.assembly, ASSEMBLY_STATES, code)
        _enum(self.binding, BINDING_STATES, code)
        _enum(self.execution_admission, ADMISSION_STATES, code)
        _enum(self.availability, AVAILABILITY_STATES, code)
        if self.source is not None:
            object.__setattr__(self, "source", _source(self.source, code))
        if self.binding in _WITH_BINDING:
            if not isinstance(self.binding_id, str) or not _TOKEN.fullmatch(
                self.binding_id
            ):
                _fail(code)
        elif self.binding_id is not None:
            _fail(code)
        if self.reason_code is not None:
            _enum(self.reason_code, DIAGNOSTIC_CODES, code)
        needs_reason = (
            self.discovery_scope == "excluded"
            or self.execution_admission == "rejected"
            or self.binding == "invalid"
            or self.availability == "unavailable"
        )
        if needs_reason == (self.reason_code is None):
            _fail(code)

    def document(self):
        value = {
            "schema_version": SCHEMA_VERSION,
            "kind": ACCESS_KIND,
            "access_id": self.access_id,
            "catalog_ref": self.catalog_ref,
            "tool_id": self.tool_id,
            "entry_key": self.entry_key,
            "provider": self.provider,
            "environment": self.environment,
            "purpose": self.purpose,
            "contract_version": self.contract_version,
            "contract_sha256": self.contract_sha256,
            "discovery_scope": self.discovery_scope,
            "assembly": self.assembly,
            "binding": self.binding,
            "execution_admission": self.execution_admission,
            "availability": self.availability,
        }
        if self.source is not None:
            value["source"] = dict(self.source)
        if self.binding_id is not None:
            value["binding_id"] = self.binding_id
        if self.reason_code is not None:
            value["reason_code"] = self.reason_code
        return value

    @classmethod
    def from_document(cls, document):
        document = dict(_validated(document, ACCESS_SCHEMA, ACCESS_KIND))
        try:
            if document.get("source") is not None:
                document["source"] = dict(document["source"])
            return cls(**document)
        except TypeError, KeyError:
            _fail("invalid_document")


@dataclass(frozen=True)
class ContractDetail:
    """The selected contract in full, expanded only at this disclosure level.

    The embedded contract is exactly the existing ToolSpec document plus its
    semantic digest; no second authoritative parameter Schema is maintained.
    """

    tool_id: str
    catalog_ref: str
    entry_key: str
    contract: Mapping
    access_id: str | None = None

    def __post_init__(self):
        code = "invalid_document"
        _entry_identity(self, code)
        if not isinstance(self.contract, Mapping):
            _fail(code)
        contract = dict(self.contract)
        if not _CONTRACT_REQUIRED <= contract.keys() <= _CONTRACT_ALLOWED:
            _fail(code)
        digest = contract.pop("contract_sha256")
        _matches(digest, _HASH, code)
        try:
            contract["environments"] = tuple(contract["environments"])
            spec = ToolSpec(**contract)
        except TypeError, KeyError:
            _fail(code)
        if spec.tool_id != self.tool_id or spec.sha256 != digest:
            _fail(code)
        object.__setattr__(
            self, "contract", {**spec.document(), "contract_sha256": digest}
        )

    def document(self):
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": CONTRACT_KIND,
            "access_id": self.access_id,
            "catalog_ref": self.catalog_ref,
            "tool_id": self.tool_id,
            "entry_key": self.entry_key,
            "contract": dict(self.contract),
        }

    @classmethod
    def from_document(cls, document):
        document = dict(_strip(document, CONTRACT_KIND))
        try:
            if document.get("contract") is not None:
                document["contract"] = dict(document["contract"])
            return cls(**document)
        except TypeError, KeyError:
            _fail("invalid_document")


def _identity_key(item):
    if isinstance(item, CandidateSummary):
        return ("candidate", item.catalog_ref, item.tool_id)
    if isinstance(item, GroupSummary):
        return ("group", item.catalog_ref, item.group_id)
    if isinstance(item, AccessEntrySummary):
        return ("access", item.access_id)
    _fail("invalid_document")


@dataclass(frozen=True)
class DiscoveryPage:
    """The result envelope: deterministic order facts and disclosure-bounded items.

    ``total`` counts disclosable results only; hidden items appear in no count,
    identifier or diagnostic. ``next_offset`` is omitted when there is no next
    page. Items are homogeneous and uniquely identified within the page.
    """

    item_kind: str
    offset: int
    limit: int
    total: int
    query: DiscoveryQuery
    items: tuple = ()
    diagnostics: tuple[DiscoveryDiagnostic, ...] = ()
    next_offset: int | None = None

    def __post_init__(self):
        code = "invalid_document"
        _enum(self.item_kind, ITEM_KINDS, code)
        _integer(self.offset, code, minimum=0)
        _integer(self.limit, code, minimum=MIN_LIMIT, maximum=MAX_LIMIT)
        _integer(self.total, code, minimum=0)
        if not isinstance(self.query, DiscoveryQuery):
            _fail(code)
        if self.next_offset is not None:
            _integer(self.next_offset, code, minimum=0)
        expected = {
            CANDIDATE_KIND: CandidateSummary,
            GROUP_KIND: GroupSummary,
            ACCESS_KIND: AccessEntrySummary,
        }[self.item_kind]
        if not isinstance(self.items, tuple) or any(
            not isinstance(item, expected) for item in self.items
        ):
            _fail(code)
        keys = [_identity_key(item) for item in self.items]
        if len(set(keys)) != len(keys):
            _fail("conflicting_identity")
        # The page carries exactly the slice its paging facts describe.
        if len(self.items) != min(max(self.total - self.offset, 0), self.limit):
            _fail(code)
        if self.total > self.offset + len(self.items):
            if self.next_offset != self.offset + len(self.items):
                _fail(code)
        elif self.next_offset is not None:
            _fail(code)
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, DiscoveryDiagnostic) for item in self.diagnostics
        ):
            _fail(code)

    def document(self):
        value = {
            "schema_version": SCHEMA_VERSION,
            "kind": PAGE_KIND,
            "item_kind": self.item_kind,
            "disclosure": "summary",
            "offset": self.offset,
            "limit": self.limit,
            "total": self.total,
            "query": self.query.document(),
            "items": [item.document() for item in self.items],
        }
        if self.next_offset is not None:
            value["next_offset"] = self.next_offset
        if self.diagnostics:
            value["diagnostics"] = [item.document() for item in self.diagnostics]
        return value

    @classmethod
    def from_document(cls, document):
        document = dict(_validated(document, PAGE_SCHEMA, PAGE_KIND))
        if document.pop("disclosure") != "summary":
            _fail("invalid_document")
        try:
            document["query"] = DiscoveryQuery.from_document(document["query"])
            parser = {
                CANDIDATE_KIND: CandidateSummary.from_document,
                GROUP_KIND: GroupSummary.from_document,
                ACCESS_KIND: AccessEntrySummary.from_document,
            }[document["item_kind"]]
            document["items"] = tuple(parser(item) for item in document["items"])
            document["diagnostics"] = tuple(
                DiscoveryDiagnostic.from_document(item)
                for item in document.pop("diagnostics", ())
            )
            return cls(**document)
        except TypeError, KeyError:
            _fail("invalid_document")


@dataclass(frozen=True)
class DiscoveryErrorDocument:
    """A query-layer error shape, kept apart from ToolResult business status."""

    code: str
    detail: str = ""

    def __post_init__(self):
        _enum(self.code, ERROR_CODES, "invalid_document")
        _bounded(self.detail, "invalid_document", maximum=512, allow_empty=True)

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
