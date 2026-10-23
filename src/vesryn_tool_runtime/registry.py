"""Explicit provider loading and Catalog composition."""

from importlib.metadata import entry_points

from .contracts import Catalog, ToolResult
from .documents import WorkflowError


class ScopedAdapter:
    def __init__(self, adapter, specs, scope):
        self.adapter, self.specs, self.scope = adapter, specs, scope

    def invoke(self, calls, context):
        admitted, results = [], {}
        for call in calls:
            try:
                self.scope.admit(self.specs[call.tool_id])
                admitted.append(call)
            except WorkflowError:
                results[call.step_id] = ToolResult(
                    "unavailable", 3, reason="Host scope does not admit this tool"
                )
        if admitted:
            results.update(self.adapter.invoke(tuple(admitted), context))
        return results


def provider(name, root):
    matches = [
        item for item in entry_points(group="vesryn.adapters") if item.name == name
    ]
    if name in {"unified", "tooling"} or len(matches) != 1:
        raise WorkflowError("Provider must name one explicit installed domain adapter")
    try:
        value = matches[0].load()(root=root)
    except Exception:  # noqa: BLE001 -- provider errors can contain private driver data
        raise WorkflowError("Domain provider could not be loaded") from None
    if not isinstance(value, Catalog):
        raise WorkflowError("Domain provider did not return Catalog")
    declared = getattr(value, "provider_name", name)
    if declared != name:
        raise WorkflowError("Domain provider identity differs from its entry point")
    value.provider_name = name
    return value


def compose(*catalogs):
    """Merge explicitly chosen providers, atomically rejecting duplicate ownership."""
    result = Catalog()
    for catalog in catalogs:
        result.merge(catalog)
    return result


def scoped_catalog(catalog, scope):
    """Wrap existing adapter groups once, retaining each tool's Provider identity."""
    result, adapters = Catalog(), {}
    for document in catalog.documents():
        spec, adapter = catalog.resolve(document["tool_id"])
        guarded = adapters.setdefault(id(adapter), ScopedAdapter(adapter, {}, scope))
        guarded.specs[spec.tool_id] = spec
        result.register(spec, guarded)
        result._providers[spec.tool_id] = catalog.provider_for(spec.tool_id)
    result.discovery_scope = scope
    for definition in catalog._assets.values():
        result.register_asset(
            definition,
            tools=tuple(
                name
                for name, asset_id in catalog._tool_assets.items()
                if asset_id == definition.asset_id
            ),
        )
    return result
