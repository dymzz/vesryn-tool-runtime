"""Thin uv source adapter: uv resolves, downloads, caches and builds the environment.

This module only translates a frozen ``AssetSelection`` into uv commands and turns
the actual outcome into the shared ``AssetReceipt``. It never walks or edits uv's
private cache, has no resolver of its own and never invokes the prepared tool.
"""

import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from filelock import FileLock, Timeout
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from .asset_index import AssetFile, AssetIndex, AssetReceipt
from .assets import AssetError, AssetSelection
from .contracts import ToolResult
from .documents import digest

_HOST_OS = {"win32": "windows", "linux": "linux", "darwin": "macos"}
_HOST_ARCH = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "arm64": "aarch64",
    "aarch64": "aarch64",
}
# Targets uv can resolve for; anything else is an unsupported target, not a guess.
_UV_PLATFORM = {
    ("windows", "x86_64"): "x86_64-pc-windows-msvc",
    ("linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("macos", "aarch64"): "aarch64-apple-darwin",
    ("macos", "x86_64"): "x86_64-apple-darwin",
}


def _host():
    return (
        _HOST_OS.get(sys.platform),
        _HOST_ARCH.get(platform.machine().lower()),
    )


def _same_version(left, right):
    try:
        return Version(left) == Version(right)
    except InvalidVersion:
        return left == right


@dataclass(frozen=True)
class UvLock:
    """A complete, hashed resolution for one target; consumable without this host.

    It describes what a container should install with ``uv pip install
    --require-hashes``. Producing it does not prepare any local environment.
    """

    selection_id: str
    artifact_id: str
    uv_version: str
    python_platform: str
    python_version: str
    requirements: str
    source_sha256: str

    @property
    def sha256(self):
        return hashlib.sha256(self.requirements.encode()).hexdigest()

    def document(self):
        return {
            "schema_version": 1,
            "kind": "tool-asset-uv-lock",
            "selection_id": self.selection_id,
            "artifact_id": self.artifact_id,
            "uv_version": self.uv_version,
            "python_platform": self.python_platform,
            "python_version": self.python_version,
            "source_sha256": self.source_sha256,
            "requirements": self.requirements,
            "requirements_sha256": self.sha256,
        }


class UvToolBackend:
    """Prepare, verify and locate uv-built CLI environments, one per artifact.

    Each artifact (asset, release, target) gets its own environment directory under
    ``root``, so versions coexist and a reuse by another consumer cannot replace
    the environment another selection points at.
    """

    def __init__(
        self,
        index,
        *,
        uv="uv",
        find_links=(),
        index_url=None,
        timeout=900,
        runner=subprocess.run,
    ):
        if not isinstance(index, AssetIndex):
            raise AssetError("invalid_selection")
        self.index = index
        self.root = index.root
        self.uv = uv
        self.find_links = tuple(find_links)
        self.index_url = index_url
        self.timeout = timeout
        self._run = runner

    # -- uv invocation -----------------------------------------------------------

    def _uv(self, *args, network, cwd=None):
        command = [self.uv, "--no-config", *args]
        if not network:
            command.insert(2, "--offline")
        return self._run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
            check=False,
        )

    def _resolver_args(self):
        args = []
        for item in self.find_links:
            args += ["--find-links", str(item)]
        if self.index_url:
            args += ["--index-url", self.index_url]
        return args

    def uv_version(self):
        """The real uv that will do the work; the caller records it with receipts."""
        try:
            result = self._uv("--version", network=True)
        except OSError:
            raise AssetError("backend_unavailable") from None
        match = re.match(r"uv (\S+)", result.stdout or "")
        if result.returncode != 0 or not match:
            raise AssetError("backend_unknown")
        return match.group(1)

    # -- selection checks --------------------------------------------------------

    @staticmethod
    def _check(selection):
        if not isinstance(selection, AssetSelection):
            raise AssetError("invalid_selection")
        release = selection.release
        if release.distribution != "python" or release.backend != "uv":
            raise AssetError("invalid_backend")
        target = selection.target
        python_platform = _UV_PLATFORM.get((target.os, target.arch))
        if python_platform is None or target.python is None:
            raise AssetError("unsupported_target")
        return python_platform

    def _directory(self, selection):
        return self.root / "uv" / ("artifact-" + selection.artifact_id)

    def _environment(self, selection):
        return self._directory(selection) / "venv"

    @staticmethod
    def _entry_path(environment, selection, *, windows):
        name = selection.release.entrypoint
        return (
            environment / "Scripts" / (name + ".exe")
            if windows
            else (environment / "bin" / name)
        )

    # -- container-consumable description ---------------------------------------

    def lock(self, selection, *, allow_network=False):
        """Resolve the full dependency set with ``uv pip compile`` for the target.

        ``tool==version`` is not a lock; the returned hashes cover every transitive
        artifact. The source wheel hash reported by uv must equal the frozen one.
        """
        python_platform = self._check(selection)
        release = selection.release
        directory = self._directory(selection)
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / "requirements.in"
        output = directory / "requirements.lock"
        source.write_text(f"{release.package} @ {release.source}\n", encoding="utf-8")
        output.unlink(missing_ok=True)
        try:
            result = self._uv(
                "pip",
                "compile",
                str(source),
                "--generate-hashes",
                "--no-header",
                "--no-annotate",
                "--python-version",
                selection.target.python,
                "--python-platform",
                python_platform,
                "--output-file",
                str(output),
                *self._resolver_args(),
                network=allow_network,
                cwd=directory,
            )
        except subprocess.TimeoutExpired:
            raise AssetError("backend_interrupted") from None
        except OSError:
            raise AssetError("backend_unavailable") from None
        if result.returncode != 0 or not output.is_file():
            raise AssetError(
                "offline_missing" if not allow_network else "resolve_failed"
            )
        text = output.read_bytes().decode("utf-8")
        self._check_source_hash(text, selection)
        return UvLock(
            selection.selection_id,
            selection.artifact_id,
            self.uv_version(),
            python_platform,
            selection.target.python,
            text,
            release.sha256,
        )

    @staticmethod
    def _check_source_hash(text, selection):
        release = selection.release
        name = canonicalize_name(release.package)
        entry = None
        for block in re.split(r"\n(?=\S)", text.replace("\\\n", "")):
            head = block.split(" @ ", 1)[0].strip()
            if " @ " in block and canonicalize_name(head) == name:
                entry = block
        if entry is None:
            raise AssetError("integrity_mismatch")
        hashes = set(re.findall(r"--hash=sha256:([0-9a-f]{64})", entry))
        if hashes != {release.sha256}:
            raise AssetError("integrity_mismatch")

    # -- preparation on this host ------------------------------------------------

    def prepare(self, selection, *, allow_network=False):
        """Build this selection's own uv environment and record the actual outcome.

        ``allow_network`` is the acquisition permission only; it never permits
        running the tool. Without it uv runs ``--offline`` and a missing artifact
        is a recorded failure. Unsupported hosts raise before anything is touched.
        """
        self._check(selection)
        if _host() != (selection.target.os, selection.target.arch):
            raise AssetError("unsupported_target")
        directory = self._directory(selection)
        directory.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(str(directory) + ".lock", timeout=self.index.timeout):
                receipt = self._build(selection, allow_network)
        except Timeout:
            raise AssetError("index_busy") from None
        return self.index.record(receipt)

    def _failure(self, selection, status, exit_code, reason, *, executed=True):
        return AssetReceipt(
            selection,
            ToolResult(
                status, exit_code, executed=executed, reason=reason, summary=reason
            ),
        )

    def _build(self, selection, allow_network):
        release = selection.release
        directory = self._directory(selection)
        environment = self._environment(selection)
        try:
            locked = self.lock(selection, allow_network=allow_network)
        except AssetError as error:
            if error.code in {"backend_unavailable"}:
                return self._failure(
                    selection, "unavailable", None, error.code, executed=False
                )
            if error.code == "backend_interrupted":
                return self._failure(selection, "interrupted", None, error.code)
            if error.code == "integrity_mismatch":
                return self._failure(selection, "failed", 1, error.code)
            return self._failure(selection, "failed", 1, error.code)
        try:
            # Only this artifact's own directory is replaced; uv's cache is untouched.
            if environment.exists():
                shutil.rmtree(environment)
            created = self._uv(
                "venv",
                str(environment),
                "--python",
                selection.target.python,
                "--no-project",
                network=allow_network,
                cwd=directory,
            )
            if created.returncode != 0:
                return self._failure(
                    selection,
                    "failed",
                    created.returncode,
                    "offline_missing" if not allow_network else "environment_failed",
                )
            installed = self._uv(
                "pip",
                "install",
                "--python",
                str(self._python(environment)),
                "--require-hashes",
                "--no-deps",
                "-r",
                str(directory / "requirements.lock"),
                *self._resolver_args(),
                network=allow_network,
                cwd=directory,
            )
        except subprocess.TimeoutExpired:
            return self._failure(selection, "interrupted", None, "backend_interrupted")
        except OSError:
            return self._failure(
                selection, "unavailable", None, "backend_unavailable", executed=False
            )
        if installed.returncode != 0:
            return self._failure(
                selection,
                "failed",
                installed.returncode,
                "offline_missing" if not allow_network else "install_failed",
            )
        try:
            facts = self._facts(selection, environment, locked.sha256)
        except AssetError as error:
            return self._failure(selection, "failed", 1, error.code)
        return AssetReceipt(
            selection,
            ToolResult("passed", 0, executed=True, complete=True, current=True),
            locator=str(environment.resolve()),
            files=facts["files"],
            environment_id=facts["environment_id"],
            verified_source_sha256=release.sha256,
        )

    @staticmethod
    def _windows():
        return sys.platform == "win32"

    def _python(self, environment):
        return environment / ("Scripts/python.exe" if self._windows() else "bin/python")

    def _facts(self, selection, environment, lock_sha256):
        """Read the real environment: installed packages, interpreter and entry file."""
        python = self._python(environment)
        listing = self._uv(
            "pip", "list", "--format", "json", "--python", str(python), network=False
        )
        if listing.returncode != 0:
            raise AssetError("backend_unknown")
        try:
            packages = {
                canonicalize_name(item["name"]): item["version"]
                for item in json.loads(listing.stdout)
            }
        except ValueError, KeyError, TypeError:
            raise AssetError("backend_unknown") from None
        release = selection.release
        actual = packages.get(canonicalize_name(release.package))
        if actual is None or not _same_version(actual, release.version):
            raise AssetError("version_mismatch")
        interpreter = self._run(
            [str(python), "-c", "import sys; print(sys.version)"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout,
            check=False,
        )
        if interpreter.returncode != 0:
            raise AssetError("backend_unknown")
        entry = self._entry_path(environment, selection, windows=self._windows())
        if not entry.is_file():
            raise AssetError("local_missing")
        with entry.open("rb") as stream:
            entry_sha = hashlib.file_digest(stream, "sha256").hexdigest()
        relative = entry.relative_to(environment).as_posix()
        return {
            "files": (AssetFile(relative, entry_sha),),
            "environment_id": digest(
                {
                    "artifact_id": selection.artifact_id,
                    "lock_sha256": lock_sha256,
                    "python": interpreter.stdout.strip(),
                    "packages": sorted(packages.items()),
                }
            ),
        }

    # -- later facts and location ------------------------------------------------

    def installed(self, selection):
        """The index fact, plus a re-check that the live environment is still whole.

        A cleared uv cache or damaged environment is reported as such instead of the
        last successful receipt. This never repairs or downloads anything.
        """
        self._check(selection)
        fact = self.index.installed(selection)
        if fact["status"] != "present":
            return fact
        environment = Path(fact["locator"])
        python = self._python(environment)
        try:
            check = self._uv("pip", "check", "--python", str(python), network=False)
            if check.returncode != 0:
                return {**fact, "status": "invalid", "reason": "environment_broken"}
            actual = self._facts(selection, environment, self._recorded_lock(selection))
        except OSError, subprocess.TimeoutExpired:
            return {**fact, "status": "unknown", "reason": "backend_unknown"}
        except AssetError as error:
            return {**fact, "status": "invalid", "reason": error.code}
        if actual["environment_id"] != fact["environment_id"]:
            return {**fact, "status": "invalid", "reason": "environment_mismatch"}
        return fact

    def _recorded_lock(self, selection):
        text = (self._directory(selection) / "requirements.lock").read_bytes()
        return hashlib.sha256(text).hexdigest()

    def command(self, catalog, selection, *, scope):
        """Return the verified entry executable for a separately admitted host.

        Acquisition permission is not execution permission: the host's scope must
        admit the tool. PATH and other installed versions are never consulted.
        """
        self._check(selection)
        spec = catalog.resolve(selection.tool_id, scope=scope)[0]
        scope.admit(spec)
        if spec.sha256 != selection.tool_contract_sha256:
            raise AssetError("selection_stale")
        fact = self.installed(selection)
        if fact["status"] != "present":
            raise AssetError(fact.get("reason", "local_missing"))
        entry = self._entry_path(
            Path(fact["locator"]), selection, windows=self._windows()
        )
        return (str(entry),)
