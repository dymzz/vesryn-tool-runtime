"""Explicit Dagger introspection and contract mapping, without executing functions.

Hosts provide invocation adapters separately. Nothing here loads a Python plugin,
approves a capability, or resolves a host path into a Dagger resource.
"""

import subprocess
import tempfile
import tomllib
from pathlib import Path

from .contracts import Catalog, ToolSpec
from .documents import WorkflowError, canonical, digest, read
from .schemas import NAME, TOOL, object_schema, validate

MODULE = {
    "type": "string",
    "pattern": r"^[a-z0-9][a-z0-9.-]+/[A-Za-z0-9._/-]+@[a-f0-9]{40}$",
}
EXPOSURES = object_schema(
    {
        "schema_version": {"const": 1, "type": "integer"},
        "module": MODULE,
        "resources": {
            "type": "object",
            "propertyNames": {"enum": ["File", "Directory"]},
            "additionalProperties": {"const": "dagger-id"},
        },
        "exposures": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "items": object_schema(
                {
                    "id": TOOL,
                    "object": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_]*$"},
                    "function": {
                        "type": "string",
                        "pattern": "^[A-Za-z][A-Za-z0-9_]*$",
                    },
                    "effect": {"enum": ["read", "check", "write"]},
                    "recovery": {"enum": ["restartable", "manual"]},
                    "environments": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": NAME,
                    },
                    "description": {"type": "string", "maxLength": 4096},
                    "domain": NAME,
                    **{
                        name: {
                            "type": "array",
                            "maxItems": 64,
                            "uniqueItems": True,
                            "items": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 128,
                            },
                        }
                        for name in ("use_when", "not_for", "tags")
                    },
                },
                ["id", "object", "function", "effect", "recovery", "environments"],
            ),
        },
    },
    ["schema_version", "module", "exposures"],
)

# Dagger TypeDefs preserve resource types that generic GraphQL ID arguments lose.
# Only interface definitions are read; no module function/constructor is called.
_BASE_TYPE = (
    "kind optional asObject { name } asScalar { name } asEnum { name values { name } }"
)
_TYPE = _BASE_TYPE
for _ in range(8):
    _TYPE = _BASE_TYPE + " asList { elementTypeDef { " + _TYPE + " } }"
INTROSPECTION = """query VesrynToolContracts {
  currentTypeDefs(returnAllTypes: false, hideCore: true) {
    kind
    asObject {
      name
      functions {
        name description
        args {
          name description defaultValue defaultPath defaultAddress ignore
          typeDef { TYPE }
        }
        returnType { TYPE }
      }
    }
  }
}""".replace("TYPE", _TYPE)


def _config(value):
    validate(value, EXPOSURES, label="Dagger exposures")
    _module(value["module"])
    identifiers = [item["id"] for item in value["exposures"]]
    if len(set(identifiers)) != len(identifiers):
        raise WorkflowError("Duplicate tool exposure")
    return value


def _module(module):
    validate(module, MODULE, label="Dagger module")
    path = module.split("@", 1)[0]
    if any(part in {"", ".", ".."} for part in path.split("/")):
        raise WorkflowError(
            "Dagger module must use a canonical remote commit reference"
        )


def load_exposures(path):
    """Read a bounded TOML allowlist; it contains purpose and policy, not Schemas."""
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise WorkflowError("Dagger exposures exceed 2 MiB")
        value = tomllib.loads(raw.decode("utf-8"))
    except OSError, UnicodeError, tomllib.TOMLDecodeError:
        raise WorkflowError("Cannot read Dagger exposures") from None
    return _config(value)


def query_schema(module, root):
    """Ask the installed Dagger CLI for structured JSON with bounded time/output.

    stderr is never published: engine errors may contain private URLs or tokens.
    Temporary files remain in the selected repository and are always removed.
    """
    _module(module)
    try:
        with tempfile.TemporaryDirectory(
            prefix=".vesryn-discovery-", dir=root
        ) as directory:
            output = Path(directory) / "schema.json"
            query = Path(directory) / "query.graphql"
            query.write_text(INTROSPECTION, encoding="utf-8")
            with output.open("wb") as stream:
                # UPSTREAM: dagger@1.0.0-beta.16 - see .agent/upstream-observations.md
                # A document file leaves the caller's terminal stdin intact.
                completed = subprocess.run(
                    [
                        "dagger",
                        "api",
                        "query",
                        "--load-module",
                        module,
                        "--doc",
                        str(query),
                    ],
                    stdout=stream,
                    stderr=subprocess.DEVNULL,
                    cwd=root,
                    timeout=120,
                    check=False,
                )
            if completed.returncode:
                raise WorkflowError(
                    "Dagger schema discovery failed; no tools registered"
                )
            return read(output)
    except subprocess.TimeoutExpired:
        raise WorkflowError(
            "Dagger schema discovery timed out; no tools registered"
        ) from None
    except OSError:
        raise WorkflowError(
            "Dagger schema discovery unavailable; check the CLI and engine"
        ) from None


class _Mapper:
    def __init__(self, schema, resources, exposures):
        if not isinstance(schema, dict):
            raise WorkflowError("Invalid Dagger introspection document")
        if len(canonical(schema)) > 2 * 1024 * 1024:
            raise WorkflowError("Dagger schema exceeds 2 MiB")
        if schema.get("errors"):
            raise WorkflowError("Dagger introspection returned errors")
        try:
            data = schema.get("data", schema)
            definitions = (
                _native_types(data["currentTypeDefs"], exposures)
                if "currentTypeDefs" in data
                else data["__schema"]["types"]
            )
            if not isinstance(definitions, list) or len(definitions) > 4096:
                raise ValueError
            self.types = {item["name"]: item for item in definitions}
            if len(self.types) != len(definitions):
                raise ValueError
        except KeyError, TypeError, ValueError:
            raise WorkflowError("Invalid Dagger introspection document") from None
        self.resources = resources

    def convert(self, reference, trail=()):
        if len(trail) > 16:
            raise WorkflowError("Dagger type nesting exceeds the mapping bound")
        kind = reference["kind"]
        if kind == "NON_NULL":
            return self._value(reference["ofType"], trail)
        return {"anyOf": [self._value(reference, trail), {"type": "null"}]}

    def _value(self, reference, trail):
        kind, name = reference["kind"], reference.get("name")
        if kind == "LIST":
            return {
                "type": "array",
                "items": self.convert(reference["ofType"], (*trail, "[]")),
            }
        if kind == "SCALAR" and name in {"String", "Boolean", "Int", "Float"}:
            return {
                "String": {"type": "string"},
                "Boolean": {"type": "boolean"},
                "Int": {"type": "integer", "minimum": -(2**31), "maximum": 2**31 - 1},
                "Float": {"type": "number"},
            }[name]
        resource = (
            name[:-2]
            if kind == "SCALAR" and isinstance(name, str) and name.endswith("ID")
            else name
        )
        if kind in {"SCALAR", "OBJECT"} and resource in self.resources:
            return object_schema(
                {"kind": {"const": resource}, "id": {"type": "string", "minLength": 1}}
            )
        if kind in {"SCALAR", "OBJECT"} and resource in {"File", "Directory"}:
            raise WorkflowError("Dagger resource requires an explicit domain mapping")
        definition = self.types.get(name)
        if not definition or definition["kind"] != kind:
            raise WorkflowError("Unsupported or inconsistent Dagger type")
        if kind == "ENUM":
            values = [item["name"] for item in definition["enumValues"]]
            if not values:
                raise WorkflowError("Dagger enum has no values")
            return {"type": "string", "enum": values}
        if kind == "INPUT_OBJECT":
            if name in trail:
                raise WorkflowError(
                    "Recursive Dagger input types require a domain mapper"
                )
            return self.inputs(definition["inputFields"], (*trail, name))
        raise WorkflowError("Dagger type requires an explicit domain mapping")

    def inputs(self, fields, trail=()):
        if not isinstance(fields, list) or len(fields) > 256:
            raise WorkflowError("Invalid or oversized Dagger argument list")
        properties, required = {}, []
        for item in fields:
            name = item["name"]
            if name in properties:
                raise WorkflowError("Duplicate Dagger argument")
            value = self.convert(item["type"], trail)
            if item.get("description"):
                value["description"] = item["description"]
            default = item["defaultValue"]
            if default is not None:
                if not isinstance(default, str):
                    raise WorkflowError("Invalid GraphQL default")
                # GraphQL literals include enum/object syntax, not necessarily JSON.
                value["x-dagger-default"] = default
            elif item["type"]["kind"] == "NON_NULL":
                required.append(name)
            properties[name] = value
        return object_schema(properties, required)


def discover(schema, exposures):
    """Map only explicitly exposed functions, failing closed on unsupported types.

    The returned ToolSpecs are candidates. A host must bind them to a trusted
    ToolAdapter with Catalog.register; discovery is never execution permission.
    """
    exposures = _config(exposures)
    mapper = _Mapper(schema, exposures.get("resources", {}), exposures["exposures"])
    result = []
    try:
        for item in exposures["exposures"]:
            owner = mapper.types[item["object"]]
            if owner["kind"] != "OBJECT":
                raise WorkflowError("Dagger exposure must reference an object function")
            fields = owner["fields"]
            if not isinstance(fields, list) or len(fields) > 4096:
                raise WorkflowError("Invalid or oversized Dagger function list")
            matches = [field for field in fields if field["name"] == item["function"]]
            if len(matches) != 1:
                raise WorkflowError("Dagger exposure must match exactly one function")
            function = matches[0]
            spec = ToolSpec(
                item["id"],
                mapper.inputs(function["args"]),
                object_schema({"value": mapper.convert(function["type"])}),
                effect=item["effect"],
                recovery=item["recovery"],
                environments=tuple(item["environments"]),
                description=item.get("description", function.get("description") or ""),
                domain=item.get("domain", ""),
                **{
                    name: tuple(item.get(name, ()))
                    for name in ("use_when", "not_for", "tags")
                },
                source={
                    "kind": "dagger",
                    "identity": exposures["module"]
                    + "#"
                    + item["object"]
                    + "."
                    + item["function"],
                    "interface_sha256": digest(
                        function.get("dagger_contract", function)
                    ),
                },
            )
            spec.validate()
            result.append(spec)
    except KeyError, TypeError, RecursionError:
        raise WorkflowError("Invalid or incomplete Dagger function contract") from None
    return tuple(result)


def _native_types(definitions, exposures):
    """Normalize typed Dagger definitions for the same explicit JSON mapper.

    This is a format adapter, not a second registry. Generic GraphQL introspection
    is also accepted for offline users, but an untyped ID is never guessed.
    """
    if not isinstance(definitions, list) or len(definitions) > 4096:
        raise WorkflowError("Invalid or oversized Dagger TypeDefs")
    types = {}
    selected = {(item["object"], item["function"]) for item in exposures}

    def reference(value, depth=0):
        if depth > 8 or type(value["optional"]) is not bool:
            raise WorkflowError("Invalid or too deeply nested Dagger TypeDef")
        kind = value["kind"]
        primitive = {
            "STRING_KIND": "String",
            "INTEGER_KIND": "Int",
            "FLOAT_KIND": "Float",
            "BOOLEAN_KIND": "Boolean",
        }
        if kind in primitive:
            result = {"kind": "SCALAR", "name": primitive[kind]}
        elif kind == "LIST_KIND":
            result = {
                "kind": "LIST",
                "ofType": reference(value["asList"]["elementTypeDef"], depth + 1),
            }
        elif kind == "OBJECT_KIND":
            result = {"kind": "OBJECT", "name": value["asObject"]["name"]}
        elif kind == "ENUM_KIND":
            enum = value["asEnum"]
            definition = {
                "kind": "ENUM",
                "name": enum["name"],
                "enumValues": enum["values"],
            }
            if enum["name"] in types and types[enum["name"]] != definition:
                raise WorkflowError("Conflicting Dagger enum definitions")
            types[enum["name"]] = definition
            result = {"kind": "ENUM", "name": enum["name"]}
        elif kind == "SCALAR_KIND":
            result = {"kind": "SCALAR", "name": value["asScalar"]["name"]}
        else:
            raise WorkflowError("Dagger TypeDef requires an explicit domain mapping")
        return result if value["optional"] else {"kind": "NON_NULL", "ofType": result}

    try:
        for definition in definitions:
            if definition["kind"] != "OBJECT_KIND":
                continue
            owner = definition["asObject"]
            name = owner["name"]
            if not any(object_name == name for object_name, _ in selected):
                continue
            if name in types:
                raise WorkflowError("Duplicate Dagger object definition")
            fields = []
            for function in owner["functions"]:
                if (name, function["name"]) not in selected:
                    continue
                fields.append(
                    {
                        "name": function["name"],
                        "description": function["description"],
                        "args": [
                            {
                                "name": arg["name"],
                                "description": arg["description"],
                                "defaultValue": None
                                if arg["defaultValue"] in (None, "")
                                else arg["defaultValue"],
                                "type": reference(arg["typeDef"]),
                            }
                            for arg in function["args"]
                        ],
                        "type": reference(function["returnType"]),
                        "dagger_contract": function,
                    }
                )
            types[name] = {"kind": "OBJECT", "name": name, "fields": fields}
    except KeyError, TypeError, RecursionError:
        raise WorkflowError("Invalid or incomplete Dagger TypeDefs") from None
    return list(types.values())


def register(catalog: Catalog, schema, exposures, adapter):
    """Bind mapped contracts through the original Catalog, using a host adapter.

    Validate the entire import and duplicate IDs before changing the Catalog.
    """
    specs = discover(schema, exposures)
    existing = {item["tool_id"] for item in catalog.documents()}
    if any(spec.tool_id in existing for spec in specs):
        raise WorkflowError("Duplicate tool registration")
    for spec in specs:
        catalog.register(spec, adapter)
    return specs
