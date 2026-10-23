"""Shared asset definition documents: independent reads and explicit assembly."""

from dataclasses import dataclass
from importlib.resources import files as resource_files
from pathlib import Path

from .assets import AssetDefinition, AssetError, AssetRelease
from .contracts import Catalog
from .documents import WorkflowError, decode, read
from .schemas import TOOL, validate

BUNDLED_DIRECTORY = "shared_assets"
DOCUMENT_KIND = "shared-asset-definitions"
SCHEMA_VERSION = 1
_ENTRY_FIELDS = frozenset({"asset_id", "catalog_revision", "releases", "tools"})


@dataclass(frozen=True)
class SharedAssetDefinition:
    """One published asset declaration plus the capabilities it is declared to serve."""

    definition: AssetDefinition
    tools: tuple[str, ...]

    def __post_init__(self):
        if not isinstance(self.definition, AssetDefinition):
            raise AssetError("invalid_definition")
        if (
            not isinstance(self.tools, tuple)
            or not self.tools
            or any(not isinstance(tool_id, str) for tool_id in self.tools)
            or len(set(self.tools)) != len(self.tools)
        ):
            raise AssetError("invalid_definition")
        for tool_id in self.tools:
            validate(tool_id, TOOL, label="shared asset capability")


def _record(entry):
    try:
        value = dict(entry)
        if set(value) != _ENTRY_FIELDS:
            raise AssetError("invalid_definition")
        releases = value["releases"]
        if not isinstance(releases, list) or not releases:
            raise AssetError("invalid_definition")
        return SharedAssetDefinition(
            AssetDefinition(
                value["asset_id"],
                value["catalog_revision"],
                tuple(AssetRelease(**release) for release in releases),
            ),
            tuple(value["tools"]),
        )
    except AssetError:
        raise
    except TypeError, KeyError, ValueError:
        raise AssetError("invalid_definition") from None


def _records(document):
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "kind", "assets"}
        or type(document["schema_version"]) is not int
        or document["schema_version"] != SCHEMA_VERSION
        or document["kind"] != DOCUMENT_KIND
        or not isinstance(document["assets"], list)
        or not document["assets"]
    ):
        raise AssetError("invalid_definition")
    records, published = [], set()
    for entry in document["assets"]:
        record = _record(entry)
        if record.definition.asset_id in published:
            raise AssetError("conflicting_asset")
        published.add(record.definition.asset_id)
        records.append(record)
    return tuple(records)


def shared_definition_documents():
    """Bundled shared-definition document names in sorted order; nothing is loaded."""
    directory = resource_files(__package__).joinpath(BUNDLED_DIRECTORY)
    try:
        return tuple(
            sorted(
                item.name
                for item in directory.iterdir()
                if item.name.endswith(".json") and item.is_file()
            )
        )
    except OSError, ValueError:
        return ()


def load_shared_definitions(source):
    """Read one shared-definitions document: a bundled name or a filesystem path.

    A pure read of published declarations: no Catalog, adapter, consumer
    environment, installation, execution permission or network access is
    involved. A bundled document name takes precedence over an equally
    named filesystem path.
    """
    if not isinstance(source, (str, Path)):
        raise WorkflowError("Cannot read a supported workflow document")
    if isinstance(source, str) and source in shared_definition_documents():
        bundled = (
            resource_files(__package__).joinpath(BUNDLED_DIRECTORY).joinpath(source)
        )
        try:
            raw = bundled.read_bytes()
        except OSError:
            raise WorkflowError("Cannot read a supported workflow document") from None
        return _records(decode(raw))
    return _records(read(source))


def register_shared_definitions(catalog, definitions):
    """Explicitly associate shared definitions with existing catalog capabilities.

    Every association reuses Catalog.register_asset: each capability must
    already be registered with its real ToolSpec and adapter, and conflicting
    ownership keeps its existing AssetError. Records apply in order; the first
    conflict raises while the associations already applied remain.
    """
    if not isinstance(catalog, Catalog):
        raise WorkflowError("Definitions assemble into the existing Catalog contract")
    if isinstance(definitions, SharedAssetDefinition):
        definitions = (definitions,)
    definitions = tuple(definitions)
    if not definitions or not all(
        isinstance(item, SharedAssetDefinition) for item in definitions
    ):
        raise AssetError("invalid_definition")
    for item in definitions:
        catalog.register_asset(item.definition, tools=item.tools)
