"""Explicit local asset receipts; no installer, engine, uv metadata or cache service."""

import hashlib
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from filelock import FileLock, Timeout

from .assets import AssetError, AssetSelection, _sha256
from .contracts import ToolResult
from .documents import ToolRuntimeError, digest, read, write
from .schemas import RESULT, validate


def asset_root(path=None, *, environ=None, platform=None):
    """Return a configurable system cache location without creating it."""
    if path is not None:
        return Path(path)
    environ = os.environ if environ is None else environ
    if environ.get("VESRYN_TOOL_ASSETS"):
        return Path(environ["VESRYN_TOOL_ASSETS"])
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        base = Path(environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    else:
        base = Path(environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "vesryn" / "tool-assets"


def native_asset_directory(root, selection):
    """Native payloads are partitioned by asset, full target, version and digest."""
    target = selection.target
    platform = f"{target.os}-{target.arch}-{digest(target.document())}"
    return (
        Path(root)
        / "native"
        / ("asset-" + selection.asset_id)
        / platform
        / ("version-" + selection.release.version)
        / selection.release.sha256
    )


@dataclass(frozen=True)
class AssetFile:
    path: str
    sha256: str

    def __post_init__(self):
        if (
            not isinstance(self.path, str)
            or not self.path
            or "\\" in self.path
            or ":" in self.path
            or "\0" in self.path
            or PurePosixPath(self.path).is_absolute()
            or any(part in {"", ".", ".."} for part in self.path.split("/"))
        ):
            raise AssetError("invalid_receipt")
        _sha256(self.sha256)


@dataclass(frozen=True)
class AssetReceipt:
    selection: AssetSelection
    outcome: ToolResult
    locator: str | None = None
    files: tuple[AssetFile, ...] = ()
    environment_id: str | None = None
    verified_source_sha256: str | None = None

    def __post_init__(self):
        if not isinstance(self.selection, AssetSelection) or not isinstance(
            self.outcome, ToolResult
        ):
            raise AssetError("invalid_receipt")
        validate(self.outcome.document(), RESULT, label="asset backend result")
        if not isinstance(self.files, tuple) or any(
            not isinstance(item, AssetFile) for item in self.files
        ):
            raise AssetError("invalid_receipt")
        if len({item.path for item in self.files}) != len(self.files):
            raise AssetError("invalid_receipt")
        if self.locator is not None and (
            not isinstance(self.locator, str) or not Path(self.locator).is_absolute()
        ):
            raise AssetError("invalid_receipt")
        if self.environment_id is not None:
            _sha256(self.environment_id)
        if self.verified_source_sha256 is not None:
            _sha256(self.verified_source_sha256)
        if (
            self.outcome.status == "passed"
            and self.verified_source_sha256 is not None
            and self.verified_source_sha256 != self.selection.release.sha256
        ):
            raise AssetError("integrity_mismatch")
        if self.outcome.status == "passed" and not (
            self.outcome.exit_code == 0
            and self.outcome.executed
            and self.outcome.complete
            and self.outcome.current
            and self.locator is not None
            and self.files
            and any(
                PurePosixPath(item.path).name
                in {
                    self.selection.release.entrypoint,
                    self.selection.release.entrypoint + ".exe",
                }
                for item in self.files
            )
            and self.verified_source_sha256 == self.selection.release.sha256
            and (
                self.selection.release.backend != "uv"
                or self.environment_id is not None
            )
        ):
            raise AssetError("backend_unknown")
        if self.outcome.status == "failed" and not self.outcome.exit_code:
            raise AssetError("invalid_receipt")

    def document(self):
        # Never retain backend stdout, parameters, outputs or raw diagnostics.
        return {
            "selection": self.selection.document(),
            "backend": self.selection.release.backend,
            "outcome": {
                key: getattr(self.outcome, key)
                for key in ("status", "exit_code", "executed", "complete", "current")
            },
            "locator": self.locator,
            "files": [asdict(item) for item in self.files],
            "environment_id": self.environment_id,
            "verified_source_sha256": self.verified_source_sha256,
        }

    @classmethod
    def from_document(cls, value):
        try:
            value = dict(value)
            backend = value.pop("backend")
            selection = AssetSelection.from_document(value.pop("selection"))
            if backend != selection.release.backend:
                raise AssetError("invalid_receipt")
            return cls(
                **{
                    **value,
                    "selection": selection,
                    "outcome": ToolResult(**value["outcome"]),
                    "files": tuple(AssetFile(**item) for item in value["files"]),
                }
            )
        except KeyError, TypeError, ValueError:
            raise AssetError("invalid_receipt") from None


class AssetIndex:
    """Readers never create files; writers merge under one interprocess file lock."""

    def __init__(self, root, *, timeout=10):
        self.root = Path(root).resolve()
        self.path = self.root / "index.json"
        self.timeout = timeout

    def _read(self):
        if not self.path.exists():
            return {}
        try:
            document = read(self.path)
            if set(document) != {"schema_version", "kind", "entries"} or (
                type(document["schema_version"]) is not int
                or document["schema_version"] != 1
                or document["kind"] != "tool-asset-index"
                or not isinstance(document["entries"], dict)
            ):
                raise AssetError("invalid_index")
            for identity, entry in document["entries"].items():
                if (
                    set(entry) != {"installation", "last_receipt", "sha256"}
                    or digest(
                        {key: entry[key] for key in ("installation", "last_receipt")}
                    )
                    != entry["sha256"]
                ):
                    raise AssetError("invalid_index")
                for key in ("installation", "last_receipt"):
                    if entry[key] is not None:
                        receipt = AssetReceipt.from_document(entry[key])
                        if receipt.selection.artifact_id != identity or (
                            key == "installation" and receipt.outcome.status != "passed"
                        ):
                            raise AssetError("invalid_index")
            return document["entries"]
        except ToolRuntimeError, KeyError, TypeError:
            raise AssetError("invalid_index") from None

    def _verify(self, receipt):
        if receipt.selection.release.backend == "oci":
            raise AssetError("backend_unknown")
        location = Path(receipt.locator).resolve()
        if receipt.selection.release.backend == "aria2" and location != (
            native_asset_directory(self.root, receipt.selection).resolve()
        ):
            raise AssetError("invalid_location")
        try:
            for item in receipt.files:
                path = location / item.path
                if not path.resolve().is_relative_to(location):
                    raise AssetError("invalid_location")
                with path.open("rb") as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
                if actual != item.sha256:
                    raise AssetError("integrity_mismatch")
        except OSError:
            raise AssetError("local_missing") from None

    def record(self, receipt):
        """Record actual backend facts; only verified success changes installation."""
        if not isinstance(receipt, AssetReceipt):
            raise AssetError("invalid_receipt")
        # Revalidate mutable ToolResult supplied by a backend before any write.
        receipt = AssetReceipt.from_document(receipt.document())
        if receipt.outcome.status == "passed":
            self._verify(receipt)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(str(self.path) + ".lock", timeout=self.timeout):
                entries = self._read()
                identity = receipt.selection.artifact_id
                previous = entries.get(identity, {})
                entry = {
                    "installation": receipt.document()
                    if receipt.outcome.status == "passed"
                    else previous.get("installation"),
                    "last_receipt": receipt.document(),
                }
                entries[identity] = {**entry, "sha256": digest(entry)}
                write(
                    self.path,
                    {
                        "schema_version": 1,
                        "kind": "tool-asset-index",
                        "entries": entries,
                    },
                    replace=True,
                )
        except Timeout:
            raise AssetError("index_busy") from None
        return receipt.document()

    def installed(self, selection):
        """Re-hash actual entry files, never infer execution permission or readiness."""
        if not isinstance(selection, AssetSelection):
            raise AssetError("invalid_selection")
        entry = self._read().get(selection.artifact_id)
        if entry is None:
            return {"status": "missing", "reason": "local_missing"}
        last = entry["last_receipt"]["outcome"]
        if entry["installation"] is None:
            uncertain = last["status"] in {
                "unknown",
                "unavailable",
                "interrupted",
                "incomplete",
            }
            return {
                "status": "unknown" if uncertain else "missing",
                "reason": "backend_unknown" if uncertain else "local_missing",
                "last_outcome": last,
            }
        receipt = AssetReceipt.from_document(entry["installation"])
        try:
            self._verify(receipt)
        except AssetError as error:
            return {
                "status": "missing" if error.code == "local_missing" else "invalid",
                "reason": error.code,
                "last_outcome": last,
            }
        return {
            "status": "present",
            "artifact_id": selection.artifact_id,
            "locator": receipt.locator,
            "environment_id": receipt.environment_id,
            "last_outcome": last,
        }
