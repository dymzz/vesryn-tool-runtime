"""Selection Binding Schema 1, integrity and current identity verification.

Workflow associations remain optional legacy metadata owned by consumers.
"""

import copy

from .documents import WorkflowError, digest
from .schemas import HASH, ID, object_schema, validate
from .scope import DiscoveryScope

SELECTION_BINDING = object_schema(
    {
        "schema_version": {"const": 1, "type": "integer"},
        "kind": {"const": "workflow-selection-binding"},
        "binding_id": HASH,
        "tool_id": {"type": "string"},
        "provider": {"type": "string"},
        "version": {"type": "string"},
        "contract_sha256": HASH,
        "contract_summary": object_schema(
            {
                "tool_id": {"type": "string"},
                "description": {"type": "string"},
                "domain": {"type": "string"},
                "effect": {"type": "string"},
                "contract_version": {"type": "string"},
                "contract_sha256": HASH,
            }
        ),
        "parameters": {"type": "object"},
        "scope": object_schema(
            {
                "repository": {"type": "string"},
                "environment": {"type": "string"},
                "permissions": {"type": "array", "items": {"type": "string"}},
            }
        ),
        "workflow": object_schema(
            {
                "definition_id": HASH,
                "generation_id": ID,
                "workflow_path": {"type": "string"},
            }
        ),
        "execution_id": {"type": ["string", "null"], "pattern": "^[a-f0-9]{32}$"},
    },
    [
        "schema_version",
        "kind",
        "binding_id",
        "tool_id",
        "provider",
        "version",
        "contract_sha256",
        "contract_summary",
        "parameters",
        "scope",
    ],
)

SELECTION_BINDING["properties"]["contract_summary"]["properties"]["display_name"] = {
    "type": "string",
    "maxLength": 120,
}


def _verify_document(binding):
    validate(binding, SELECTION_BINDING, label="selection binding")
    if binding["binding_id"] != digest(canonical_binding(binding)):
        raise WorkflowError(
            "Selection binding integrity check failed (tampered binding)"
        )


def _provider_matches(provider, catalog, tool_id):
    if provider != catalog.provider_for(tool_id):
        raise WorkflowError(
            "Selection binding Provider does not match the loaded catalog"
        )


def canonical_binding(binding):
    """Deterministic canonical representation excluding computed binding_id."""
    return {k: v for k, v in binding.items() if k != "binding_id"}


def verify_binding(binding, catalog, *, current_scope=None):
    """Verify selection binding integrity and reject stale or altered contracts."""
    _verify_document(binding)
    current_scope = current_scope or DiscoveryScope()
    for key in ("repository", "environment"):
        current = getattr(current_scope, key)
        if current and binding["scope"][key] != current:
            raise WorkflowError(f"Selection binding {key} scope mismatch")
    if current_scope.permissions is not None:
        bound_perms = set(binding["scope"]["permissions"])
        if not bound_perms.issubset(current_scope.permissions):
            raise WorkflowError("Selection binding permission scope mismatch")

    spec, adapter = catalog.resolve(binding["tool_id"], scope=current_scope)

    if spec.contract_version != binding["version"]:
        raise WorkflowError(
            f"Tool contract version changed from {binding['version']} to {spec.contract_version}; "
            "refuse to use stale binding; do not auto-select latest"
        )

    if spec.sha256 != binding["contract_sha256"]:
        raise WorkflowError(
            "Tool contract sha256 changed; refuse to use stale binding; do not auto-select latest"
        )

    _provider_matches(binding["provider"], catalog, binding["tool_id"])
    bound_scope = DiscoveryScope(
        repository=binding["scope"]["repository"],
        environment=binding["scope"]["environment"],
        permissions=frozenset(binding["scope"]["permissions"]),
    )
    catalog.resolve(binding["tool_id"], scope=bound_scope)
    summary = binding["contract_summary"]
    if any(
        summary[key] != spec.summary()[key]
        for key in ("tool_id", "effect", "contract_version", "contract_sha256")
    ):
        raise WorkflowError("Selection binding contract summary differs from its tool")
    validate(binding["parameters"], spec.input_schema, label="tool parameters")
    return spec, adapter


def create_binding(catalog, tool_id, *, provider, parameters=None, scope=None):
    """Freeze one explicit selection; a binding digest never grants permission."""
    scope = scope or DiscoveryScope()
    _provider_matches(provider, catalog, tool_id)
    spec, _ = catalog.resolve(tool_id, scope=scope)
    parameters = {} if parameters is None else copy.deepcopy(parameters)
    validate(parameters, spec.input_schema, label="tool parameters")
    value = {
        "schema_version": 1,
        "kind": "workflow-selection-binding",
        "tool_id": spec.tool_id,
        "provider": provider,
        "version": spec.contract_version,
        "contract_sha256": spec.sha256,
        "contract_summary": spec.summary(),
        "parameters": parameters,
        "scope": {
            "repository": scope.repository or "",
            "environment": scope.environment or "",
            "permissions": sorted(scope.permissions) if scope.permissions else [],
        },
        "execution_id": None,
    }
    value["binding_id"] = digest(canonical_binding(value))
    _verify_document(value)
    return value


verify_document = _verify_document
