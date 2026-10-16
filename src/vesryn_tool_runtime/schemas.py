"""Normative JSON Schema 2020-12 documents, also exported by the host CLI."""

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry
from referencing.exceptions import Unresolvable

from .documents import WorkflowError

DRAFT = "https://json-schema.org/draft/2020-12/schema"
NAME = {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"}
ID = {"type": "string", "pattern": "^[a-f0-9]{32}$"}
HASH = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
TOOL = {"type": "string", "pattern": "^[a-z][a-z0-9-]*\\.[a-z][a-z0-9-]*$"}


def object_schema(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }


CONTRACT_VERSION = {"type": "string", "pattern": "^[1-9][0-9]*(?:\\.[0-9]+){0,2}$"}

RESULT = object_schema(
    {
        "status": {
            "enum": [
                "passed",
                "failed",
                "incomplete",
                "unavailable",
                "interrupted",
                "unknown",
            ]
        },
        "exit_code": {"type": ["integer", "null"]},
        "outputs": {"type": "object"},
        **{
            key: {"type": "boolean"}
            for key in ("executed", "complete", "current", "reused", "report_generated")
        },
        "reason": {"type": ["string", "null"]},
    }
)
RESULT["properties"]["summary"] = {"type": "string", "maxLength": 1000}

TOOL_DESCRIPTOR = {
    "$schema": DRAFT,
    **object_schema(
        {
            "tool_id": TOOL,
            "contract_version": CONTRACT_VERSION,
            "input_schema": {"type": ["object", "boolean"]},
            "output_schema": {"type": ["object", "boolean"]},
            "effect": {"enum": ["read", "check", "write"]},
            "recovery": {"enum": ["restartable", "manual"]},
            "reuse": {"const": "verified_identity"},
            "environments": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": NAME,
            },
        }
    ),
}
TOOL_DESCRIPTOR["properties"]["contract_sha256"] = HASH
TOOL_DESCRIPTOR["properties"].update(
    display_name={"type": "string", "maxLength": 120},
    description={"type": "string", "maxLength": 4096},
    domain=NAME,
    **{
        name: {
            "type": "array",
            "maxItems": 64,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": 128},
        }
        for name in ("use_when", "not_for", "tags")
    },
    source=object_schema(
        {
            "kind": NAME,
            "identity": {"type": "string", "minLength": 1, "maxLength": 1024},
            "interface_sha256": HASH,
        }
    ),
)


TOOL_EVENT = {
    "$schema": DRAFT,
    **object_schema(
        {
            "schema_version": {"const": 1, "type": "integer"},
            "kind": {"const": "tool-invocation-observation"},
            "event": {"enum": ["invoking", "returned", "rejected"]},
            "observed_ns": {"type": "integer", "minimum": 0},
            "tool_id": TOOL,
            "invocation_id": ID,
            "execution_id": ID,
            "batch_id": ID,
            "batch_size": {"type": "integer", "minimum": 1},
            "attempt": {"type": "integer", "minimum": 1},
            "contract_version": CONTRACT_VERSION,
            "contract_sha256": HASH,
            **{
                key: RESULT["properties"][key]
                for key in (
                    "status",
                    "exit_code",
                    "executed",
                    "complete",
                    "current",
                    "reused",
                    "report_generated",
                )
            },
            "result_validation": {"enum": ["valid", "invalid", "not_executed"]},
            "execution_status": {
                "enum": [*RESULT["properties"]["status"]["enum"], None]
            },
            "result_exit_code": {"type": ["integer", "null"]},
        },
        [
            "schema_version",
            "kind",
            "event",
            "observed_ns",
            "tool_id",
            "invocation_id",
            "batch_id",
            "batch_size",
            "attempt",
            "contract_version",
            "contract_sha256",
        ],
    ),
}


def validate(value, schema, *, label="document"):
    """Validate offline; diagnostic paths never include invalid instance values."""
    try:
        Draft202012Validator(schema, registry=Registry()).validate(value)
    except (ValidationError, Unresolvable, TypeError, RecursionError) as error:
        path = "/".join(str(item) for item in getattr(error, "absolute_path", ()))
        raise WorkflowError(f"Invalid {label} at /{path}") from None


def check_schema(schema):
    """Accept standard schemas with local references; no network schema retrieval."""

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"$ref", "$dynamicRef"} and not item.startswith("#"):
                    raise WorkflowError("Tool schemas must use local references")
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    try:
        visit(schema)
        Draft202012Validator.check_schema(schema)
    except WorkflowError:
        raise
    except SchemaError, TypeError, AttributeError, RecursionError:
        raise WorkflowError("Invalid tool JSON Schema") from None
