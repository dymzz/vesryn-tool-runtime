"""Unified tool registration records: tools as primary keys, groups by reference.

Issue #14's registration layer (TR-DISC-01B): a real tool registers directly
as a ``ToolAsset`` — no empty ToolSpec or placeholder capability is required —
and ``ToolGroup`` members reference tools by their ``tool_id`` primary key.
Access entries reuse the delivered #27 ``AccessEntrySummary`` record and its
identity rules; this module adds no new identity scheme. Registration is an
in-memory fact: it grants no installation, binding or execution, and a tool
without a real entry contract gets no fabricated callable entry.
"""

import re
from dataclasses import dataclass

from .assets import AssetDefinition, AssetError, _token
from .schemas import TOOL, validate

_GROUP = re.compile(TOOL["pattern"])


@dataclass(frozen=True)
class ToolAsset:
    """One registered tool: its primary key and its immutable asset definition.

    ``tool_id`` is the tool primary key. It may be a bare program identity
    (``trivy``) or a real, source-backed capability ID (``python.dead-code``);
    registering an asset never requires a capability contract to exist.
    """

    tool_id: str
    definition: AssetDefinition
    display_name: str = ""
    description: str = ""

    def __post_init__(self):
        _token(self.tool_id)
        if not isinstance(self.definition, AssetDefinition):
            raise AssetError("invalid_definition")
        for value, limit in ((self.display_name, 120), (self.description, 4096)):
            if not isinstance(value, str) or len(value) > limit:
                raise AssetError("invalid_definition")


@dataclass(frozen=True)
class ToolGroup:
    """A named group whose members reference registered tools by primary key.

    ``group_id`` keeps the delivered #27 group grammar (``domain.group``).
    Aliases are match aids only and never create capability identities; the
    display metadata is preserved by registration and disclosed as-is.
    """

    group_id: str
    members: tuple[str, ...]
    display_name: str = ""
    description: str = ""
    aliases: tuple[str, ...] = ()

    def __post_init__(self):
        validate(self.group_id, TOOL, label="tool group identity")
        if (
            not isinstance(self.members, tuple)
            or not self.members
            or len(set(self.members)) != len(self.members)
        ):
            raise AssetError("invalid_definition")
        for member in self.members:
            _token(member)
        for value, limit in ((self.display_name, 120), (self.description, 4096)):
            if not isinstance(value, str) or len(value) > limit:
                raise AssetError("invalid_definition")
        for alias in self.aliases:
            if not isinstance(alias, str) or not alias or len(alias) > 128:
                raise AssetError("invalid_definition")
        if len(set(self.aliases)) != len(self.aliases):
            raise AssetError("invalid_definition")
